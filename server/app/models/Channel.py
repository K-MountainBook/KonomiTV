
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import requests
import time
import traceback
from tortoise import fields
from tortoise import models
from tortoise import timezone
from tortoise import transactions
from tortoise.exceptions import IntegrityError
from typing import Any, cast, Literal, TYPE_CHECKING

from app.constants import API_REQUEST_HEADERS, CONFIG
from app.utils import Jikkyo
from app.utils import Logging
from app.utils import TSInformation
from app.utils.EDCB import CtrlCmdUtil
from app.utils.EDCB import EDCBUtil

if TYPE_CHECKING:
    from app.models import Program


class Channel(models.Model):

    # データベース上のテーブル名
    class Meta:
        table: str = 'channels'

    # テーブル設計は Notion を参照のこと
    id: str = fields.CharField(255, pk=True)  # type: ignore
    display_channel_id: str = fields.CharField(255, unique=True)  # type: ignore
    network_id: int = fields.IntField()
    service_id: int = fields.IntField()
    transport_stream_id: int | None = fields.IntField(null=True)
    remocon_id: int = fields.IntField()
    channel_number: str = fields.CharField(255)  # type: ignore
    type: str = fields.CharField(255)  # type: ignore
    name: str = fields.TextField()
    jikkyo_force: int | None = fields.IntField(null=True)
    is_subchannel: bool = fields.BooleanField()  # type: ignore
    is_radiochannel: bool = fields.BooleanField()  # type: ignore
    is_watchable: bool = fields.BooleanField()  # type: ignore
    # 本当は型を追加したいが、元々動的に追加される追加カラムなので、型を追加すると諸々エラーが出る
    ## 実際の値は Channel モデルの利用側で Channel.getCurrentAndNextProgram() を呼び出して取得する
    ## モデルの取得は非同期のため、@property は使えない
    program_present: Any
    program_following: Any

    @property
    def is_display(self) -> bool:
        # サブチャンネルでかつ現在の番組情報が両方存在しないなら、表示フラグを False に設定
        # 現在放送されているサブチャンネルのみをチャンネルリストに表示するような挙動とする
        # 一般的にサブチャンネルは常に放送されているわけではないため、放送されていない時にチャンネルリストに表示する必要はない
        if self.is_subchannel is True and self.program_present is None:
            return False
        return True

    @property
    def viewer_count(self) -> int:
        # 現在の視聴者数を取得
        from app.models import LiveStream
        return LiveStream.getViewerCount(self.display_channel_id)


    @classmethod
    async def update(cls) -> None:
        """ チャンネル情報を更新する """

        timestamp = time.time()
        Logging.info('Channels updating...')

        try:
            # Mirakurun バックエンド
            if CONFIG['general']['backend'] == 'Mirakurun':
                await cls.updateFromMirakurun()

            # EDCB バックエンド
            elif CONFIG['general']['backend'] == 'EDCB':
                await cls.updateFromEDCB()
        except:
            traceback.print_exc()

        Logging.info(f'Channels update complete. ({round(time.time() - timestamp, 3)} sec)')


    @classmethod
    async def updateFromMirakurun(cls) -> None:
        """ Mirakurun バックエンドからチャンネル情報を取得し、更新する """

        # このトランザクションはパフォーマンス向上と、チャンネル情報を一時的に削除してから再生成するまでの間に API リクエストが来た場合に
        # "Specified display_channel_id was not found" エラーでフロントエンドを誤動作させるのを防ぐためのもの
        async with transactions.in_transaction():

            # この変数から更新対象のチャンネル情報を削除していき、残った古いチャンネル情報を最後にまとめて削除する
            duplicate_channels = {temp.id:temp for temp in await Channel.filter(is_watchable=True)}

            # Mirakurun の API からチャンネル情報を取得する
            try:
                mirakurun_services_api_url = f'{CONFIG["general"]["mirakurun_url"]}/api/services'
                mirakurun_services_api_response = await asyncio.to_thread(requests.get,
                    url = mirakurun_services_api_url,
                    headers = API_REQUEST_HEADERS,
                    timeout = 5,
                )
                if mirakurun_services_api_response.status_code != 200:  # Mirakurun からエラーが返ってきた
                    Logging.error(f'Failed to get channels from Mirakurun. (HTTP Error {mirakurun_services_api_response.status_code})')
                    raise Exception(f'Failed to get channels from Mirakurun. (HTTP Error {mirakurun_services_api_response.status_code})')
                services = mirakurun_services_api_response.json()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as ex:
                Logging.error(f'Failed to get channels from Mirakurun. (Connection Timeout)')
                raise ex

            # 同じネットワーク ID のサービスのカウント
            same_network_id_counts: dict[int, int] = {}

            # 同じリモコン番号のサービスのカウント
            same_remocon_id_counts: dict[int, int] = {}

            for service in services:

                # type が 0x01 (デジタルTVサービス) / 0x02 (デジタル音声サービス) / 0xa1 (161: 臨時映像サービス) /
                # 0xa2 (162: 臨時音声サービス) / 0xad (173: 超高精細度4K専用TVサービス) 以外のサービスを弾く
                ## ワンセグ・データ放送 (type:0xC0) やエンジニアリングサービス (type:0xA4) など
                ## 詳細は ARIB STD-B10 第2部 6.2.13 に記載されている
                ## https://web.archive.org/web/20140427183421if_/http://www.arib.or.jp/english/html/overview/doc/2-STD-B10v5_3.pdf#page=153
                if service['type'] not in [0x01, 0x02, 0xa1, 0xa2, 0xad]:
                    continue

                # 不明なネットワーク ID のチャンネルを弾く
                if TSInformation.getNetworkType(service['networkId']) == 'OTHER':
                    continue

                # チャンネル ID
                channel_id = f'NID{service["onid"]}-SID{service["sid"]:03d}'

                # 既にレコードがある場合は更新、ない場合は新規作成
                duplicate_channel = duplicate_channels.pop(channel_id, None)
                if duplicate_channel is None:
                    channel = Channel()
                else:
                    channel = duplicate_channel

                # 取得してきた値を設定
                channel.id = f'NID{service["networkId"]}-SID{service["serviceId"]:03d}'
                channel.service_id = int(service['serviceId'])
                channel.network_id = int(service['networkId'])
                channel.remocon_id = int(service['remoteControlKeyId']) if ('remoteControlKeyId' in service) else -1
                channel.type = TSInformation.getNetworkType(channel.network_id)
                channel.name = TSInformation.formatString(service['name'])
                channel.jikkyo_force = None
                channel.is_watchable = True

                # すでに放送が終了した「FOXスポーツ＆エンターテインメント」「BSスカパー」「Dlife」を除外
                ## 放送終了後にチャンネルスキャンしていないなどの理由でバックエンド側にチャンネル情報が残っている場合がある
                if channel.type == 'BS' and channel.service_id in [238, 241, 258]:
                    continue

                # チャンネルタイプが STARDIGIO でサービス ID が 400 ～ 499 以外のチャンネルを除外
                # だいたい謎の試験チャンネルとかで見るに耐えない
                if channel.type == 'STARDIGIO' and not 400 <= channel.service_id <= 499:
                    continue

                # 「試験チャンネル」という名前（前方一致）のチャンネルを除外
                # CATV や SKY に存在するが、だいたいどれもやってないし表示されてるだけ邪魔
                if channel.name.startswith('試験チャンネル'):
                    continue

                # type が 0x02 のサービスのみ、ラジオチャンネルとして設定する
                # 今のところ、ラジオに該当するチャンネルは放送大学ラジオとスターデジオのみ
                channel.is_radiochannel = True if (service['type'] == 0x02) else False

                # 同じネットワーク内にあるサービスのカウントを追加
                if channel.network_id not in same_network_id_counts:  # まだキーが存在しないとき
                    same_network_id_counts[channel.network_id] = 0
                same_network_id_counts[channel.network_id] += 1  # カウントを足す

                # ***** チャンネル番号・チャンネル ID を算出 *****

                # 地デジ: リモコン番号からチャンネル番号を算出する
                if channel.type == 'GR':

                    # 同じリモコン番号のサービスのカウントを定義
                    if channel.remocon_id not in same_remocon_id_counts:  # まだキーが存在しないとき
                        # 011(-0), 011-1, 011-2 のように枝番をつけるため、ネットワーク ID とは異なり -1 を基点とする
                        same_remocon_id_counts[channel.remocon_id] = -1

                    # 同じネットワーク内にある最初のサービスのときだけ、同じリモコン番号のサービスのカウントを追加
                    # これをやらないと、サブチャンネルまで枝番処理の対象になってしまう
                    if same_network_id_counts[channel.network_id] == 1:
                        same_remocon_id_counts[channel.remocon_id] += 1

                    # 上2桁はリモコン番号から、下1桁は同じネットワーク内にあるサービスのカウント
                    channel.channel_number = str(channel.remocon_id).zfill(2) + str(same_network_id_counts[channel.network_id])

                    # 同じリモコン番号のサービスが複数ある場合、枝番をつける
                    if same_remocon_id_counts[channel.remocon_id] > 0:
                        channel.channel_number += '-' + str(same_remocon_id_counts[channel.remocon_id])

                # BS・CS・CATV・STARDIGIO: サービス ID をそのままチャンネル番号・リモコン番号とする
                elif (channel.type == 'BS' or
                    channel.type == 'CS' or
                    channel.type == 'CATV' or
                    channel.type == 'STARDIGIO'):
                    channel.remocon_id = channel.service_id  # ソートする際の便宜上設定しておく
                    channel.channel_number = str(channel.service_id).zfill(3)

                    # BS のみ、一部のチャンネルに決め打ちでチャンネル番号を割り当てる
                    if channel.type == 'BS':
                        if 101 <= channel.service_id <= 102:
                            channel.remocon_id = 1
                        elif 103 <= channel.service_id <= 104:
                            channel.remocon_id = 3
                        elif 141 <= channel.service_id <= 149:
                            channel.remocon_id = 4
                        elif 151 <= channel.service_id <= 159:
                            channel.remocon_id = 5
                        elif 161 <= channel.service_id <= 169:
                            channel.remocon_id = 6
                        elif 171 <= channel.service_id <= 179:
                            channel.remocon_id = 7
                        elif 181 <= channel.service_id <= 189:
                            channel.remocon_id = 8
                        elif 191 <= channel.service_id <= 193:
                            channel.remocon_id = 9
                        elif 200 <= channel.service_id <= 202:
                            channel.remocon_id = 10
                        elif channel.service_id == 211:
                            channel.remocon_id = 11
                        elif channel.service_id == 222:
                            channel.remocon_id = 12

                # SKY: サービス ID を 1024 で割った余りをチャンネル番号・リモコン番号とする
                ## SPHD (network_id=10) のチャンネル番号は service_id - 32768 、
                ## SPSD (SKYサービス系: network_id=3) のチャンネル番号は service_id - 16384 で求められる
                ## 両者とも 1024 の倍数なので、1024 で割った余りからチャンネル番号が算出できる
                elif channel.type == 'SKY':
                    channel.remocon_id = channel.service_id % 1024  # ソートする際の便宜上設定しておく
                    channel.channel_number = str(channel.service_id % 1024).zfill(3)

                # チャンネルID = チャンネルタイプ(小文字)+チャンネル番号
                channel.display_channel_id = channel.type.lower() + channel.channel_number

                # ***** サブチャンネルかどうかを算出 *****

                # 地デジ: サービス ID に 0x0187 を AND 演算（ビットマスク）した時に 0 でない場合
                ## 地デジのサービス ID は、ARIB TR-B14 第五分冊 第七編 9.1 によると
                ## (地域種別:6bit)(県複フラグ:1bit)(サービス種別:2bit)(地域事業者識別:4bit)(サービス番号:3bit) の 16bit で構成されている
                ## 0x0187 はビット単位に直すと 0b0000000110000111 になるので、AND 演算でビットマスク（1以外のビットを強制的に0に設定）すると、
                ## サービス種別とサービス番号だけが取得できる  ビットマスクした値のサービス種別が 0（テレビ型）でサービス番号が 0（プライマリサービス）であれば
                ## メインチャンネルと判定できるし、そうでなければサブチャンネルだと言える
                if channel.type == 'GR':
                    channel.is_subchannel = (channel.service_id & 0x0187) != 0

                # BS: Mirakurun から得られる情報からはサブチャンネルかを判定できないため、決め打ちで設定
                elif channel.type == 'BS':
                    # サービス ID が以下のリストに含まれるかどうか
                    if ((channel.service_id in [102, 104]) or
                        (142 <= channel.service_id <= 149) or
                        (152 <= channel.service_id <= 159) or
                        (162 <= channel.service_id <= 169) or
                        (172 <= channel.service_id <= 179) or
                        (182 <= channel.service_id <= 189) or
                        (channel.service_id in [232, 233])):
                        channel.is_subchannel = True
                    else:
                        channel.is_subchannel = False

                # それ以外: サブチャンネルという概念自体がないため一律で False に設定
                else:
                    channel.is_subchannel = False

                # レコードを保存する
                await channel.save()

            # 不要なチャンネル情報を削除する
            for duplicate_channel in duplicate_channels.values():
                await duplicate_channel.delete()


    @classmethod
    async def updateFromEDCB(cls) -> None:
        """ EDCB バックエンドからチャンネル情報を取得し、更新する """

        # このトランザクションはパフォーマンス向上と、チャンネル情報を一時的に削除してから再生成するまでの間に API リクエストが来た場合に
        # "Specified display_channel_id was not found" エラーでフロントエンドを誤動作させるのを防ぐためのもの
        async with transactions.in_transaction():

            # この変数から更新対象のチャンネル情報を削除していき、残った古いチャンネル情報を最後にまとめて削除する
            duplicate_channels = {temp.id:temp for temp in await Channel.filter(is_watchable=True)}

            # リモコン番号が取得できない場合に備えてバックアップ
            backup_remocon_ids: dict[str, int] = {channel.id: channel.remocon_id for channel in await Channel.filter(is_watchable=True)}

            # CtrlCmdUtil を初期化
            edcb = CtrlCmdUtil()
            edcb.setConnectTimeOutSec(5)  # 5秒後にタイムアウト

            # EDCB の ChSet5.txt からチャンネル情報を取得する
            services = await edcb.sendFileCopy('ChSet5.txt')
            if services is not None:
                services = EDCBUtil.parseChSet5(EDCBUtil.convertBytesToString(services))
                # 枝番処理がミスらないようソートしておく
                services.sort(key = lambda temp: temp['onid'] * 100000 + temp['sid'])
            else:
                Logging.error('Failed to get channels from EDCB.')
                raise Exception('Failed to get channels from EDCB.')

            # EDCB から EPG 由来のチャンネル情報を取得する
            ## sendEnumService() の情報源は番組表で、期限切れなどで番組情報が1つもないサービスについては取得できない
            ## あればラッキー程度の情報と考えてほしい
            epg_services: list[dict[str, Any]] = await edcb.sendEnumService() or []

            # 同じネットワーク ID のサービスのカウント
            same_network_id_counts: dict[int, int] = {}

            # 同じリモコン番号のサービスのカウント
            same_remocon_id_counts: dict[int, int] = {}

            for service in services:

                # type が 0x01 (デジタルTVサービス) / 0x02 (デジタル音声サービス) / 0xa1 (161: 臨時映像サービス) /
                # 0xa2 (162: 臨時音声サービス) / 0xad (173: 超高精細度4K専用TVサービス) 以外のサービスを弾く
                ## ワンセグ・データ放送 (type:0xC0) やエンジニアリングサービス (type:0xA4) など
                ## 詳細は ARIB STD-B10 第2部 6.2.13 に記載されている
                ## https://web.archive.org/web/20140427183421if_/http://www.arib.or.jp/english/html/overview/doc/2-STD-B10v5_3.pdf#page=153
                if service['service_type'] not in [0x01, 0x02, 0xa1, 0xa2, 0xad]:
                    continue

                # 不明なネットワーク ID のチャンネルを弾く
                if TSInformation.getNetworkType(service['onid']) == 'OTHER':
                    continue

                # チャンネル ID
                channel_id = f'NID{service["onid"]}-SID{service["sid"]:03d}'

                # 既にレコードがある場合は更新、ない場合は新規作成
                duplicate_channel = duplicate_channels.pop(channel_id, None)
                if duplicate_channel is None:
                    channel = Channel()
                else:
                    channel = duplicate_channel

                # 取得してきた値を設定
                channel.id = channel_id
                channel.service_id = int(service['sid'])
                channel.network_id = int(service['onid'])
                channel.transport_stream_id = int(service['tsid'])
                channel.remocon_id = -1
                channel.type = TSInformation.getNetworkType(channel.network_id)
                channel.name = TSInformation.formatString(service['service_name'])
                channel.jikkyo_force = None
                channel.is_watchable = True

                # すでに放送が終了した「FOXスポーツ＆エンターテインメント」「BSスカパー」「Dlife」を除外
                ## 放送終了後にチャンネルスキャンしていないなどの理由でバックエンド側にチャンネル情報が残っている場合がある
                if channel.type == 'BS' and channel.service_id in [238, 241, 258]:
                    continue

                # チャンネルタイプが STARDIGIO でサービス ID が 400 ～ 499 以外のチャンネルを除外
                # だいたい謎の試験チャンネルとかで見るに耐えない
                if channel.type == 'STARDIGIO' and not 400 <= channel.service_id <= 499:
                    continue

                # 「試験チャンネル」という名前（前方一致）のチャンネルを除外
                # CATV や SKY に存在するが、だいたいどれもやってないし表示されてるだけ邪魔
                if channel.name.startswith('試験チャンネル'):
                    continue

                # type が 0x02 のサービスのみ、ラジオチャンネルとして設定する
                # 今のところ、ラジオに該当するチャンネルは放送大学ラジオとスターデジオのみ
                channel.is_radiochannel = True if (service['service_type'] == 0x02) else False

                # 同じネットワーク内にあるサービスのカウントを追加
                if channel.network_id not in same_network_id_counts:  # まだキーが存在しないとき
                    same_network_id_counts[channel.network_id] = 0
                same_network_id_counts[channel.network_id] += 1  # カウントを足す

                # ***** チャンネル番号・チャンネル ID を算出 *****

                # 地デジ: リモコン番号からチャンネル番号を算出する
                if channel.type == 'GR':

                    # EPG 由来のチャンネル情報を取得
                    ## 現在のチャンネルのリモコン番号が含まれる
                    ## EDCB では EPG 由来のチャンネル情報からしかリモコン番号の情報を取得できない
                    epg_service = next(filter(lambda temp: temp['onid'] == channel.network_id and temp['sid'] == channel.service_id, epg_services), None)

                    if epg_service is not None:
                        # EPG 由来のチャンネル情報が取得できていればリモコン番号を取得
                        channel.remocon_id = int(epg_service['remote_control_key_id'])
                    else:
                        # 取得できなかったので、あれば以前のバックアップからリモコン番号を取得
                        channel.remocon_id = cast(int, backup_remocon_ids.get(channel.id, -1))

                        # それでもリモコン番号が不明の時は、同じネットワーク ID を持つ別サービスのリモコン番号を取得する
                        ## 地上波の臨時サービスはリモコン番号が取得できないことが多い問題への対応
                        if channel.remocon_id <= 0:
                            for temp in epg_services:
                                if temp['onid'] == channel.network_id and temp['sid'] != channel.service_id:
                                    channel.remocon_id = int(temp['remote_control_key_id'])
                                    break

                    # 同じリモコン番号のサービスのカウントを定義
                    if channel.remocon_id not in same_remocon_id_counts:  # まだキーが存在しないとき
                        # 011(-0), 011-1, 011-2 のように枝番をつけるため、ネットワーク ID とは異なり -1 を基点とする
                        same_remocon_id_counts[channel.remocon_id] = -1

                    # 同じネットワーク内にある最初のサービスのときだけ、同じリモコン番号のサービスのカウントを追加
                    # これをやらないと、サブチャンネルまで枝番処理の対象になってしまう
                    if same_network_id_counts[channel.network_id] == 1:
                        same_remocon_id_counts[channel.remocon_id] += 1

                    # 上2桁はリモコン番号から、下1桁は同じネットワーク内にあるサービスのカウント
                    channel.channel_number = str(channel.remocon_id).zfill(2) + str(same_network_id_counts[channel.network_id])

                    # 同じリモコン番号のサービスが複数ある場合、枝番をつける
                    if same_remocon_id_counts[channel.remocon_id] > 0:
                        channel.channel_number += '-' + str(same_remocon_id_counts[channel.remocon_id])

                # BS・CS・CATV・STARDIGIO: サービス ID をそのままチャンネル番号・リモコン番号とする
                elif (channel.type == 'BS' or
                    channel.type == 'CS' or
                    channel.type == 'CATV' or
                    channel.type == 'STARDIGIO'):
                    channel.remocon_id = channel.service_id  # ソートする際の便宜上設定しておく
                    channel.channel_number = str(channel.service_id).zfill(3)

                    # BS のみ、一部のチャンネルに決め打ちでチャンネル番号を割り当てる
                    if channel.type == 'BS':
                        if 101 <= channel.service_id <= 102:
                            channel.remocon_id = 1
                        elif 103 <= channel.service_id <= 104:
                            channel.remocon_id = 3
                        elif 141 <= channel.service_id <= 149:
                            channel.remocon_id = 4
                        elif 151 <= channel.service_id <= 159:
                            channel.remocon_id = 5
                        elif 161 <= channel.service_id <= 169:
                            channel.remocon_id = 6
                        elif 171 <= channel.service_id <= 179:
                            channel.remocon_id = 7
                        elif 181 <= channel.service_id <= 189:
                            channel.remocon_id = 8
                        elif 191 <= channel.service_id <= 193:
                            channel.remocon_id = 9
                        elif 200 <= channel.service_id <= 202:
                            channel.remocon_id = 10
                        elif channel.service_id == 211:
                            channel.remocon_id = 11
                        elif channel.service_id == 222:
                            channel.remocon_id = 12

                # SKY: サービス ID を 1024 で割った余りをチャンネル番号・リモコン番号とする
                ## SPHD (network_id=10) のチャンネル番号は service_id - 32768 、
                ## SPSD (SKYサービス系: network_id=3) のチャンネル番号は service_id - 16384 で求められる
                ## 両者とも 1024 の倍数なので、1024 で割った余りからチャンネル番号が算出できる
                elif channel.type == 'SKY':
                    channel.remocon_id = channel.service_id % 1024  # ソートする際の便宜上設定しておく
                    channel.channel_number = str(channel.service_id % 1024).zfill(3)

                # チャンネルID = チャンネルタイプ(小文字)+チャンネル番号
                channel.display_channel_id = channel.type.lower() + channel.channel_number

                # ***** サブチャンネルかどうかを算出 *****

                # 地デジ: サービス ID に 0x0187 を AND 演算（ビットマスク）した時に 0 でない場合
                ## 地デジのサービス ID は、ARIB TR-B14 第五分冊 第七編 9.1 によると
                ## (地域種別:6bit)(県複フラグ:1bit)(サービス種別:2bit)(地域事業者識別:4bit)(サービス番号:3bit) の 16bit で構成されている
                ## 0x0187 はビット単位に直すと 0b0000000110000111 になるので、AND 演算でビットマスク（1以外のビットを強制的に0に設定）すると、
                ## サービス種別とサービス番号だけが取得できる  ビットマスクした値のサービス種別が 0（テレビ型）でサービス番号が 0（プライマリサービス）であれば
                ## メインチャンネルと判定できるし、そうでなければサブチャンネルだと言える
                if channel.type == 'GR':
                    channel.is_subchannel = (channel.service_id & 0x0187) != 0

                # BS: EDCB から得られる情報からはサブチャンネルかを判定できないため、決め打ちで設定
                elif channel.type == 'BS':
                    # サービス ID が以下のリストに含まれるかどうか
                    if ((channel.service_id in [102, 104]) or
                        (142 <= channel.service_id <= 149) or
                        (152 <= channel.service_id <= 159) or
                        (162 <= channel.service_id <= 169) or
                        (172 <= channel.service_id <= 179) or
                        (182 <= channel.service_id <= 189) or
                        (channel.service_id in [232, 233])):
                        channel.is_subchannel = True
                    else:
                        channel.is_subchannel = False

                # それ以外: サブチャンネルという概念自体がないため一律で False に設定
                else:
                    channel.is_subchannel = False

                # レコードを保存する
                try:
                    await channel.save()
                # 既に登録されているチャンネルならスキップ
                except IntegrityError:
                    pass

            # 不要なチャンネル情報を削除する
            for duplicate_channel in duplicate_channels.values():
                await duplicate_channel.delete()


    @classmethod
    async def updateJikkyoStatus(cls) -> None:
        """ チャンネル情報のうち、ニコニコ実況関連のステータスを更新する """

        # 全ての実況チャンネルのステータスを更新
        await Jikkyo.updateStatus()

        # 全てのチャンネル情報を取得
        channels = await Channel.filter(is_watchable=True)

        # チャンネル情報ごとに
        for channel in channels:

            # 実況チャンネルのステータスを取得
            jikkyo = Jikkyo(channel.network_id, channel.service_id)
            status = await jikkyo.getStatus()

            # ステータスが None（実況チャンネル自体が存在しないか、コミュニティの場合で実況枠が存在しない）でなく、force が -1 でなければ
            if status != None and status['force'] != -1:

                # ステータスを更新
                channel.jikkyo_force = status['force']
                await channel.save()


    async def getCurrentAndNextProgram(self) -> tuple[Program | None, Program | None]:
        """
        現在と次の番組情報を取得する

        Returns:
            tuple[Program | None, Program | None]: 現在と次の番組情報が入ったタプル
        """

        # モジュール扱いになるのを避けるためここでインポート
        from app.models import Program

        # 現在時刻
        now = timezone.now()

        # 現在の番組情報を取得する
        program_present = await Program.filter(
            channel_id = self.id,  # 同じ channel_id (ex: NID32736-SID1024)
            start_time__lte = now,  # 番組開始時刻が現在時刻以下
            end_time__gte = now,  # 番組終了時刻が現在時刻以上
        ).order_by('-start_time').first()

        # 次の番組情報を取得する
        program_following = await Program.filter(
            channel_id = self.id,  # 同じ channel_id (ex: NID32736-SID1024)
            start_time__gte = now,  # 番組開始時刻が現在時刻以上
        ).order_by('start_time').first()

        # 現在の番組情報、次の番組情報のタプルを返す
        return (program_present, program_following)
