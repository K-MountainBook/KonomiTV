
/**
 * 共通ユーティリティ
 */
export default class Utils {

    // バージョン情報
    // ビルド時の環境変数 (vue.config.js に記載) から取得
    static readonly version: string = process.env.VUE_APP_VERSION;

    // バックエンドの API のベース URL
    static readonly api_base_url = (() => {
        if (process.env.NODE_ENV === 'development') {
            // デバッグ時はポートを 7000 に強制する
            return `${window.location.protocol}//${window.location.hostname}:7000/api`;
        } else {
            // ビルド後は同じポートを使う
            return `${window.location.protocol}//${window.location.host}/api`;
        }
    })();


    /**
     * アクセストークンを LocalStorage から取得する
     * @returns JWT アクセストークン（ログインしていない場合は null が返る）
     */
    static getAccessToken(): string | null {

        // LocalStorage の取得結果をそのまま返す
        // LocalStorage.getItem() はキーが存在しなければ（=ログインしていなければ）null を返す
        return localStorage.getItem('KonomiTV-AccessToken');
    }


    /**
     * アクセストークンを LocalStorage に保存する
     * @param access_token 発行された JWT アクセストークン
     */
    static saveAccessToken(access_token: string): void {

        // そのまま LocalStorage に保存
        localStorage.setItem('KonomiTV-AccessToken', access_token);
    }


    /**
     * アクセストークンを LocalStorage から削除する
     * アクセストークンを削除することで、ログアウト相当になる
     */
    static deleteAccessToken(): void {

        // LocalStorage に KonomiTV-AccessToken キーが存在しない
        if (localStorage.getItem('KonomiTV-AccessToken') === null) return;

        // KonomiTV-AccessToken キーを削除
        localStorage.removeItem('KonomiTV-AccessToken');
    }


    /**
     * ブラウザが実行されている OS に応じて、"Alt" または "Option" を返す
     * キーボードショートカットのコンビネーションキーの説明を OS によって分けるために使う
     * @returns ブラウザが実行されている OS が Mac なら Option を、それ以外なら Alt を返す
     */
    static AltOrOption(): 'Alt' | 'Option' {
        // iPhone・iPad で純正キーボードを接続した場合も一応想定して、iPhone・iPad も含める（動くかは未検証）
        return /iPhone|iPad|Macintosh/i.test(navigator.userAgent) ? 'Option' : 'Alt';
    }


    /**
     * ブラウザが実行されている OS に応じて、"Ctrl" または "Cmd" を返す
     * キーボードショートカットのコンビネーションキーの説明を OS によって分けるために使う
     * @returns ブラウザが実行されている OS が Mac なら Cmd を、それ以外なら Ctrl を返す
     */
    static CtrlOrCmd(): 'Ctrl' | 'Cmd' {
        // iPhone・iPad で純正キーボードを接続した場合も一応想定して、iPhone・iPad も含める（動くかは未検証）
        return /iPhone|iPad|Macintosh/i.test(navigator.userAgent) ? 'Cmd' : 'Ctrl';
    }


    /**
     * Blob に格納されているデータをブラウザにダウンロードさせる
     * @param blob Blob オブジェクト
     * @param filename 保存するファイル名
     */
    static downloadBlobData(blob: Blob, filename: string): void {

        // Blob URL を発行
        const blob_url = URL.createObjectURL(blob);

        // 画像をダウンロード
        const link = document.createElement('a');
        link.download = filename;
        link.href = blob_url;
        link.click();

        // Blob URL を破棄
        URL.revokeObjectURL(blob_url);
    }


    /**
     * innerHTML しても問題ないように HTML の特殊文字をエスケープする
     * PHP の htmlspecialchars() と似たようなもの
     * @param content HTML エスケープされてないテキスト
     * @returns HTML エスケープされたテキスト
     */
    static escapeHTML(content: string): string {

        // HTML エスケープが必要な文字
        // ref: https://www.php.net/manual/ja/function.htmlspecialchars.php
        const html_escape_table = {
            '&': '&amp;',
            '"': '&quot;',
            '\'': '&apos;',
            '<': '&lt;',
            '>': '&gt;',
        };

        // ref: https://qiita.com/noriaki/items/4bfef8d7cf85dc1035b3
        return content.replace(/[&"'<>]/g, (match) => {
            return html_escape_table[match];
        });
    }


    /**
     * OAuth 連携時のポップアップを画面中央に表示するための windowFeatures 文字列を取得する
     * ref: https://qiita.com/catatsuy/items/babce8726ea78f5d25b1
     * @returns window.open() で使う windowFeatures 文字列
     */
    static getWindowFeatures(): string {

        // ポップアップウインドウのサイズ
        const popupSizeWidth = 650;
        const popupSizeHeight = window.screen.height >= 800 ? 800 : window.screen.height - 100;

        // ポップアップウインドウの位置
        const posTop = (window.screen.height - popupSizeHeight) / 2;
        const posLeft = (window.screen.width - popupSizeWidth) / 2;

        return `toolbar=0,status=0,top=${posTop},left=${posLeft},width=${popupSizeWidth},height=${popupSizeHeight},modal=yes,alwaysRaised=yes`;
    }


    /**
     * 現在フォーカスを持っている要素に指定された CSS クラスが付与されているか
     * @param class_name 存在を確認する CSS クラス名
     * @returns document.activeElement が class_name で指定したクラスを持っているかどうか
     */
    static hasActiveElementClass(class_name: string): boolean {
        if (document.activeElement === null) return false;
        return document.activeElement.classList.contains(class_name);
    }


    /**
     * ブラウザが Firefox かどうか
     * @returns ブラウザが Firefox なら true を返す
     */
    static isFirefox(): boolean {
        return /Firefox/i.test(navigator.userAgent);
    }


    /**
     * モバイルデバイス（スマホ・タブレット）かどうか
     * @returns モバイルデバイス (スマホ・タブレット) なら true を返す
     */
    static isMobileDevice(): boolean {
        // Macintosh が入っているのは、iPadOS は既定でデスクトップ表示モードが有効になっていて、UA だけでは Mac と判別できないため
        // Mac にタッチパネル付きの機種は存在しないので、'ontouchend' in document で判定できる
        return /iPhone|iPad|iPod|Macintosh|Android|Mobile/i.test(navigator.userAgent) && 'ontouchend' in document;
    }


    /**
     * 表示画面がスマホ横画面かどうか
     * @returns スマホ横画面なら true を返す
     */
    static isSmartphoneHorizontal(): boolean {
        return window.matchMedia('(max-width: 1000px) and (max-height: 450px)').matches;
    }


    /**
     * 表示画面がスマホ縦画面かどうか
     * @returns スマホ縦画面なら true を返す
     */
    static isSmartphoneVertical(): boolean {
        return window.matchMedia('(max-width: 600px) and (min-height: 450.01px)').matches;
    }


    /**
     * 表示画面がタブレット横画面かどうか
     * @returns タブレット横画面なら true を返す
     */
    static isTabletHorizontal(): boolean {
        return window.matchMedia('(max-width: 1264px) and (max-height: 850px)').matches;
    }


    /**
     * 表示画面がタブレット縦画面かどうか
     * @returns タブレット縦画面なら true を返す
     */
    static isTabletVertical(): boolean {
        return window.matchMedia('(max-width: 850px) and (min-height: 850.01px)').matches;
    }


    /**
     * 表示端末がタッチデバイスかどうか
     * @returns タッチデバイスなら true を返す
     */
    static isTouchDevice(): boolean {
        return window.matchMedia('(hover: none)').matches;
    }


    /**
     * 任意の桁で切り捨てする
     * ref: https://qiita.com/nagito25/items/0293bc317067d9e6c560#comment-87f0855f388953843037
     * @param value 切り捨てする数値
     * @param base どの桁で切り捨てするか (-1 → 10の位 / 3 → 小数第3位）
     * @return 切り捨てした値
     */
    static mathFloor(value: number, base: number = 0): number {
        return Math.floor(value * (10**base)) / (10**base);
    }


    /**
     * async/await でスリープ的なもの
     * @param seconds 待機する秒数 (ミリ秒単位ではないので注意)
     * @returns Promise を返すので、await sleep(1); のように使う
     */
    static async sleep(seconds: number): Promise<number> {
        return await new Promise(resolve => setTimeout(resolve, seconds * 1000));
    }


    /**
     * 現在時刻の UNIX タイムスタンプ (秒単位) を取得する (デバッグ用)
     * @returns 現在時刻の UNIX タイムスタンプ (秒単位)
     */
    static time(): number {
        return Date.now() / 1000;
    }


    /**
     * 指定された値の型の名前を取得する
     * ref: https://qiita.com/amamamaou/items/ef0b797156b324bb4ef3
     * @returns 指定された値の型の名前
     */
    static typeof(value: any): string {
        return Object.prototype.toString.call(value).slice(8, -1).toLowerCase();
    }


    /**
     * 文字列中に含まれる URL をリンクの HTML に置き換える
     * @param text 置換対象の文字列
     * @returns URL をリンクに置換した文字列
     */
    static URLtoLink(text: string): string {

        // HTML の特殊文字で表示がバグらないように、事前に HTML エスケープしておく
        text = Utils.escapeHTML(text);

        // ref: https://www.softel.co.jp/blogs/tech/archives/6099
        const pattern = /(https?:\/\/[-A-Z0-9+&@#/%?=~_|!:,.;]*[-A-Z0-9+&@#/%=~_|])/ig;
        return text.replace(pattern, '<a href="$1" target="_blank">$1</a>');
    }
}
