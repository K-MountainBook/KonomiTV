<template>
    <!-- ベース画面の中にそれぞれの設定画面で異なる部分を記述する -->
    <SettingsBase>
        <h2 class="settings__heading">
            <router-link v-ripple class="settings__back-button" to="/settings/">
                <Icon icon="fluent:arrow-left-12-filled" width="25px" />
            </router-link>
            <Icon icon="bi:chat-left-text-fill" width="19px" />
            <span class="ml-3">ニコニコ実況</span>
        </h2>
        <div class="settings__content" :class="{'settings__content--loading': is_loading}">
            <div class="niconico-account niconico-account--anonymous" v-if="userStore.user === null || userStore.user.niconico_user_id === null">
                <div class="niconico-account-wrapper">
                    <Icon class="flex-shrink-0" icon="bi:chat-left-text-fill" width="45px" />
                    <div class="niconico-account__info ml-4">
                        <div class="niconico-account__info-name">
                            <span class="niconico-account__info-name-text">ニコニコアカウントと連携していません</span>
                        </div>
                        <span class="niconico-account__info-description">
                            ニコニコアカウントと連携すると、テレビを見ながらニコニコ実況にコメントできるようになります。
                        </span>
                    </div>
                </div>
                <v-btn class="niconico-account__login ml-auto" color="secondary" width="130" height="56" depressed
                    @click="loginNiconicoAccount()">
                    <Icon icon="fluent:plug-connected-20-filled" class="mr-2" height="26" />連携する
                </v-btn>
            </div>
            <div class="niconico-account" v-if="userStore.user !== null && userStore.user.niconico_user_id !== null">
                <div class="niconico-account-wrapper">
                    <img class="niconico-account__icon" :src="userStore.user_niconico_icon_url">
                    <div class="niconico-account__info">
                        <div class="niconico-account__info-name">
                            <span class="niconico-account__info-name-text">{{userStore.user.niconico_user_name}} と連携しています</span>
                        </div>
                        <span class="niconico-account__info-description">
                            <span class="mr-2" style="white-space: nowrap;">Niconico User ID:</span>
                            <a class="mr-2" :href="`https://www.nicovideo.jp/user/${userStore.user.niconico_user_id}`"
                                target="_blank">{{userStore.user.niconico_user_id}}</a>
                            <span class="secondary--text" v-if="userStore.user.niconico_user_premium == true">(Premium)</span>
                        </span>
                    </div>
                </div>
                <v-btn class="niconico-account__login ml-auto" color="secondary" width="130" height="56" depressed
                    @click="logoutNiconicoAccount()">
                    <Icon icon="fluent:plug-disconnected-20-filled" class="mr-2" height="26" />連携解除
                </v-btn>
            </div>
            <div class="settings__item mt-7">
                <div class="settings__item-heading">コメントのミュート設定</div>
                <div class="settings__item-label">
                    表示したくないコメントを、映像上やコメントリストに表示しないようにミュートできます。<br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-4" depressed @click="comment_mute_settings_modal = !comment_mute_settings_modal">
                <Icon icon="heroicons-solid:filter" height="19px" />
                <span class="ml-1">コメントのミュート設定を開く</span>
            </v-btn>
            <div class="settings__item">
                <div class="settings__item-heading">コメントの速さ</div>
                <div class="settings__item-label">
                    プレイヤーに流れるコメントの速さを設定します。<br>
                    たとえば 1.2 に設定すると、コメントが 1.2 倍速く流れます。<br>
                </div>
                <v-slider class="settings__item-form" ticks="always" thumb-label hide-details
                    :step="0.1" :min="0.5" :max="2" v-model="settingsStore.settings.comment_speed_rate">
                </v-slider>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">コメントの文字サイズ</div>
                <div class="settings__item-label">
                    プレイヤーに流れるコメントの文字サイズの基準値を設定します。<br>
                    実際の文字サイズは画面サイズに合わせて調整されます。デフォルトの文字サイズは 34px です。<br>
                </div>
                <v-slider class="settings__item-form" ticks="always" thumb-label hide-details
                    :min="20" :max="60" v-model="settingsStore.settings.comment_font_size">
                </v-slider>
            </div>
            <div class="settings__item settings__item--switch">
                <label class="settings__item-heading" for="close_comment_form_after_sending">コメント送信後にコメント入力フォームを閉じる</label>
                <label class="settings__item-label" for="close_comment_form_after_sending">
                    この設定をオンにすると、コメントを送信した後に、コメント入力フォームが自動で閉じるようになります。<br>
                    コメント入力フォームが表示されたままだと、大半のショートカットキーが文字入力と競合して使えなくなります。とくに理由がなければ、オンにしておくのがおすすめです。<br>
                </label>
                <v-switch class="settings__item-switch" id="close_comment_form_after_sending" inset hide-details
                    v-model="settingsStore.settings.close_comment_form_after_sending">
                </v-switch>
            </div>
        </div>
        <CommentMuteSettings v-model="comment_mute_settings_modal" />
    </SettingsBase>
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import Vue from 'vue';

import CommentMuteSettings from '@/components/Settings/CommentMuteSettings.vue';
import Niconico from '@/services/Niconico';
import useSettingsStore from '@/store/SettingsStore';
import useUserStore from '@/store/UserStore';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

export default Vue.extend({
    name: 'Settings-Jikkyo',
    components: {
        SettingsBase,
        CommentMuteSettings,
    },
    data() {
        return {

            // コメントのミュート設定のモーダルを表示するか
            comment_mute_settings_modal: false,

            // ローディング中かどうか
            is_loading: true,
        };
    },
    computed: {
        // SettingsStore / UserStore に this.settingsStore / this.userStore でアクセスできるようにする
        // ref: https://pinia.vuejs.org/cookbook/options-api.html
        ...mapStores(useSettingsStore, useUserStore),
    },
    async created() {

        // アカウント情報を更新
        await this.userStore.fetchUser();

        // ローディング状態を解除
        this.is_loading = false;

        // もしハッシュ (# から始まるフラグメント) に何か指定されていたら、
        // OAuth 連携のコールバックの結果が入っている可能性が高いので、パースを試みる
        // アカウント情報更新より後にしないと Snackbar がうまく表示されない
        if (location.hash !== '') {
            const params = new URLSearchParams(location.hash.replace('#', ''));
            if (params.get('status') !== null && params.get('detail') !== null) {
                // コールバックの結果を取得できたので、OAuth 連携の結果を画面に通知する
                const authorization_status = parseInt(params.get('status')!);
                const authorization_detail = params.get('detail')!;
                this.onOAuthCallbackReceived(authorization_status, authorization_detail);
                // URL からフラグメントを削除
                // ref: https://stackoverflow.com/a/49373716/17124142
                history.replaceState(null, '', ' ');
            }
        }
    },
    methods: {
        async loginNiconicoAccount() {

            // ログインしていない場合はエラーにする
            if (this.userStore.is_logged_in === false) {
                this.$message.warning('連携をはじめるには、KonomiTV アカウントにログインしてください。');
                return;
            }

            // ニコニコアカウントと連携するための認証 URL を取得
            const authorization_url = await Niconico.fetchAuthorizationURL();
            if (authorization_url === null) {
                return;
            }

            // モバイルデバイスではポップアップが事実上使えない (特に Safari ではブロックされてしまう) ので、素直にリダイレクトで実装する
            if (Utils.isMobileDevice() === true) {
                location.href = authorization_url;
                return;
            }

            // OAuth 連携のため、認証 URL をポップアップウインドウで開く
            // window.open() の第2引数はユニークなものにしておくと良いらしい
            // ref: https://qiita.com/catatsuy/items/babce8726ea78f5d25b1 (大変参考になりました)
            const popup_window = window.open(authorization_url, 'KonomiTV-OAuthPopup', Utils.getWindowFeatures());
            if (popup_window === null) {
                this.$message.error('ポップアップウインドウを開けませんでした。');
                return;
            }

            // 認証完了 or 失敗後、ポップアップウインドウから送信される文字列を受信
            const onMessage = async (event) => {

                // すでにウインドウが閉じている場合は実行しない
                if (popup_window.closed) return;

                // 受け取ったオブジェクトに KonomiTV-OAuthPopup キーがない or そもそもオブジェクトではない際は実行しない
                // ブラウザの拡張機能から結構余計な message が飛んでくるっぽい…。
                if (Utils.typeof(event.data) !== 'object') return;
                if (('KonomiTV-OAuthPopup' in event.data) === false) return;

                // 認証は完了したので、ポップアップウインドウを閉じ、リスナーを解除する
                if (popup_window) popup_window.close();
                window.removeEventListener('message', onMessage);

                // ステータスコードと詳細メッセージを取得
                const authorization_status = event.data['KonomiTV-OAuthPopup']['status'] as number;
                const authorization_detail = event.data['KonomiTV-OAuthPopup']['detail'] as string;
                this.onOAuthCallbackReceived(authorization_status, authorization_detail);
            };

            // postMessage() を受信するリスナーを登録
            window.addEventListener('message', onMessage);
        },

        async onOAuthCallbackReceived(authorization_status: number, authorization_detail: string) {
            console.log(`NiconicoAuthCallbackAPI: Status: ${authorization_status} / Detail: ${authorization_detail}`);

            // OAuth 連携に失敗した
            if (authorization_status !== 200) {
                if (authorization_detail.startsWith('Authorization was denied (access_denied)')) {
                    this.$message.error('ニコニコアカウントとの連携がキャンセルされました。');
                } else if (authorization_detail.startsWith('Failed to get access token (HTTP Error ')) {
                    const error = authorization_detail.replace('Failed to get access token ', '');
                    this.$message.error(`アクセストークンの取得に失敗しました。${error}`);
                } else if (authorization_detail.startsWith('Failed to get access token (Connection Timeout)')) {
                    this.$message.error('アクセストークンの取得に失敗しました。ニコニコで障害が発生している可能性があります。');
                } else if (authorization_detail.startsWith('Failed to get user information (HTTP Error ')) {
                    const error = authorization_detail.replace('Failed to get user information ', '');
                    this.$message.error(`ニコニコアカウントのユーザー情報の取得に失敗しました。${error}`);
                } else if (authorization_detail.startsWith('Failed to get user information (Connection Timeout)')) {
                    this.$message.error('ニコニコアカウントのユーザー情報の取得に失敗しました。ニコニコで障害が発生している可能性があります。');
                } else {
                    this.$message.error(`ニコニコアカウントとの連携に失敗しました。(${authorization_detail})`);
                }
                return;
            }

            // アカウント情報を強制的に更新
            await this.userStore.fetchUser(true);

            this.$message.success('ニコニコアカウントと連携しました。');
        },

        async logoutNiconicoAccount() {

            // ニコニコアカウント連携解除 API にリクエスト
            const result = await Niconico.logoutAccount();
            if (result === false) {
                return;
            }

            // アカウント情報を強制的に更新
            await this.userStore.fetchUser(true);

            this.$message.success('ニコニコアカウントとの連携を解除しました。');
        },
    }
});

</script>
<style lang="scss" scoped>

.settings__content {
    opacity: 1;
    transition: opacity 0.4s;

    &--loading {
        opacity: 0;
    }
}

.niconico-account {
    display: flex;
    align-items: center;
    height: 120px;
    padding: 20px;
    border-radius: 15px;
    background: var(--v-background-lighten2);
    @include tablet-horizontal {
        align-items: normal;
        flex-direction: column;
        height: auto;
        padding: 16px;
    }
    @include tablet-vertical {
        align-items: normal;
        flex-direction: column;
        height: auto;
        padding: 16px;
        .niconico-account-wrapper {
            .niconico-account__info {
                margin-left: 16px !important;
                margin-right: 0 !important;
                &-name-text {
                    font-size: 18.5px;
                }
                &-description {
                    font-size: 13.5px;
                }
            }
        }
    }
    @include smartphone-horizontal {
        align-items: normal;
        flex-direction: column;
        height: auto;
        padding: 16px;
        border-radius: 10px;
        .niconico-account-wrapper {
            .niconico-account__info {
                margin-right: 0 !important;
            }
        }
    }
    @include smartphone-horizontal-short {
        .niconico-account-wrapper {
            .niconico-account__info {
                margin-left: 16px !important;
                &-name-text {
                    font-size: 18px;
                }
                &-description {
                    font-size: 13px;
                }
            }
        }
    }
    @include smartphone-vertical {
        align-items: normal;
        flex-direction: column;
        height: auto;
        padding: 16px 12px;
        border-radius: 10px;
        .niconico-account-wrapper {
            .niconico-account__info {
                margin-left: 12px !important;
                margin-right: 0px !important;
                &-name-text {
                    font-size: 17px;
                }
                &-description {
                    font-size: 13px;
                }
            }
        }
    }

    &--anonymous {
        @include tablet-vertical {
            .niconico-account__login {
                margin-top: 12px;
            }
        }
        @include smartphone-horizontal {
            .niconico-account__login {
                margin-top: 12px;
            }
        }
        @include smartphone-horizontal-short {
            .niconico-account-wrapper {
                svg {
                    display: none;
                }
                .niconico-account__info {
                    margin-left: 0 !important;
                }
            }
        }
        @include smartphone-vertical {
            padding-top: 20px;
            .niconico-account__login {
                margin-top: 16px;
            }
            .niconico-account-wrapper {
                svg {
                    display: none;
                }
                .niconico-account__info {
                    margin-left: 0 !important;
                    margin-right: 0 !important;
                }
            }
        }
    }

    &-wrapper {
        display: flex;
        align-items: center;
        min-width: 0;
        height: 80px;
        @include smartphone-vertical {
            height: 60px;
        }
    }

    &__icon {
        flex-shrink: 0;
        min-width: 80px;
        height: 100%;
        border-radius: 50%;
        object-fit: cover;
        // 読み込まれるまでのアイコンの背景
        background: linear-gradient(150deg, var(--v-gray-base), var(--v-background-lighten2));
        // 低解像度で表示する画像がぼやけないようにする
        // ref: https://sho-log.com/chrome-image-blurred/
        image-rendering: -webkit-optimize-contrast;
        @include smartphone-vertical {
            width: 60px;
            min-width: 60px;
            height: 60px;
        }
    }

    &__info {
        display: flex;
        flex-direction: column;
        min-width: 0;
        margin-left: 20px;
        margin-right: 16px;

        &-name {
            display: inline-flex;
            align-items: center;
            height: 33px;
            @include smartphone-vertical {
                height: auto;
            }

            &-text {
                display: inline-block;
                font-size: 20px;
                color: var(--v-text-base);
                font-weight: bold;
                overflow: hidden;
                white-space: nowrap;
                text-overflow: ellipsis;  // はみ出た部分を … で省略
            }
        }

        &-description {
            display: inline-block;
            margin-top: 4px;
            color: var(--v-text-darken1);
            font-size: 14px;
        }
    }

    &__login {
        border-radius: 7px;
        font-size: 16px;
        letter-spacing: 0;
        @include tablet-horizontal {
            height: 50px !important;
            margin-top: 12px;
            margin-right: auto;
        }
        @include tablet-vertical {
            height: 42px !important;
            margin-top: 8px;
            margin-right: auto;
            font-size: 14.5px;
        }
        @include smartphone-horizontal {
            height: 42px !important;
            margin-top: 8px;
            margin-right: auto;
            font-size: 14.5px;
        }
        @include smartphone-vertical {
            height: 42px !important;
            margin-top: 16px;
            margin-right: auto;
            font-size: 14.5px;
        }
    }
}

</style>