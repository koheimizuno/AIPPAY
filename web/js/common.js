/**
 * ラジオボタンで選択された値を取得する
 */
function getRadioSelected(name) {

    let elems = $(`input[name='${name}']`);

    for (let i = 0; i < elems.length; i++) {
        let elem = elems.eq(i);
        if (elem.prop("checked")) return elem.val();
    }

    return null;

}

/**
 * ローディング表示を開始する
 */
function showLoadingOverlay() {
    let elem = $("#loading-overlay");
    elem.removeClass("ji-hidden");
}

/**
 * ローディング表示を終了する
 */
function hideLoadingOverlay() {
    let elem = $("#loading-overlay");
    elem.addClass("ji-hidden");
}

/**
 * メッセージの表示
 */
function showMessage(message) {

    let dlg = $("#infoDialog");

    dlg.find(".idp-body > p").text(message);
    dlg.removeClass("d-none");

}

/**
 * 日付を表すテキストをマークアップする
 */
function markupDateText(val) {

    return val;

}

/**
 * ラベルとコンテンツで構成される要素を生成する
 */
function createLabelContentItem(wrap_tag, elem_tag, label, content) {
    let wp = $(`<${wrap_tag}></<${wrap_tag}>`);
    let el = $(`<${elem_tag} class="label"></${elem_tag}>`).text(label);
    wp.append(el);
    el = $(`<${elem_tag} class="content"></${elem_tag}>`).text(content);
    wp.append(el);
    return wp;
}
