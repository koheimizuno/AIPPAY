/**
 * 一覧上に権利の情報を表示する
 */
function showOnList(data) {

    // 更新対象の行を取得する
    let tbl = $("#ji-tbl-main");
    let row = tbl.find("#row-" + data.Id);

    // 表示
    row.find(".cell-addr").text(data.MailAddress ?? "");
    row.find(".cell-name").text(data.Name ?? "");
    row.find(".cell-org").text(data.Organization ?? "");
    if (data.IsStaff) {
        row.find(".badge-staff").removeClass("d-none");
    } else {
        row.find(".badge-staff").addClass("d-none");
    }
    if (data.IsAdmin) {
        row.find(".badge-admin").removeClass("d-none");
    } else {
        row.find(".badge-admin").addClass("d-none");
    }
    row.find(".cell-login").text(data.LastLogInTime_DateTime ?? "");
    row.find("button").val(data.Id);

}

/**
 * 編集ダイアログ上の情報を最新にする
 */
function showOnDialog(data) {

    // ダイアログ
    let dlg = $("#dlg1");

    // 組織、名前
    dlg.find(".dlg1-org").val(data.Organization ?? "");
    dlg.find(".dlg1-name").val(data.Name ?? "");

    // メールアドレス
    dlg.find(".dlg1-addr").val(data.MailAddress ?? "");

    // 権限
    dlg.find(".dlg1-is-client").prop("checked", data.IsClient);
    dlg.find(".dlg1-is-staff").prop("checked", data.IsStaff);
    dlg.find(".dlg1-is-staff").prop("disabled", data.Me);
    dlg.find(".dlg1-is-admin").prop("checked", data.IsAdmin);
    dlg.find(".dlg1-is-admin").prop("disabled", data.Me);

    // 追加アドレス
    dlg.find(".dlg1-cc-addr-0").val(data.CcAddress_0 ?? "");
    dlg.find(".dlg1-cc-addr-1").val(data.CcAddress_1 ?? "");
    dlg.find(".dlg1-cc-addr-2").val(data.CcAddress_2 ?? "");

}

/**
 * 詳細ダイアログを開く
 */
function openEditDialog(e) {

    // IDの取得
    btn = $(e.currentTarget);
    let id = btn.val();
    $("#dlg1 .dlg1-id").val(id);

    // APIに問い合わせ
    $.ajax({
        url: '/s/users/api/get',
        type: 'POST',
        dataType: 'json',
        data: { Id: id }
    })
    .done((data) => {

        // ダイアログ上に表示
        showOnDialog(data);

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        console.log(textStatus);
    })
    .always(() => {
    });

    // ダイアログの表示
    $("#dlg1").modal("show");

}

/**
 * 更新する
 */
function updateUser() {

    let p = {};

    // IDを取得
    p.Id = $("#dlg1 .dlg1-id").val();

    // 値の検証と収集
    let dlg = $("#dlg1");
    let v = null;

    v = dlg.find(".dlg1-org").val();
    if (v) p.Organization = v;

    v = dlg.find(".dlg1-name").val();
    if (v) p.Name = v;

    v = dlg.find(".dlg1-addr").val();
    if (v) p.MailAddress = v;

    p.IsClient = 1;
    if (dlg.find(".dlg1-is-staff").prop("checked")) p.IsStaff = 1;
    if (dlg.find(".dlg1-is-admin").prop("checked")) p.IsAdmin = 1;

    // 追加アドレス
    v = dlg.find(".dlg1-cc-addr-0").val();
    if (v) p.CcAddress_0 = v;
    v = dlg.find(".dlg1-cc-addr-1").val();
    if (v) p.CcAddress_1 = v;
    v = dlg.find(".dlg1-cc-addr-2").val();
    if (v) p.CcAddress_2 = v;

    // APIに投げる
    $.ajax({
        url: '/s/users/api/update',
        type: 'POST',
        dataType: 'json',
        data: p
    })
    .done((data) => {

        if (data.Result) {
            // 更新結果で画面を更新する
            showOnDialog(data);
            showOnList(data);
            // 成功したらモーダルを閉じる
            dlg.modal("hide");
        } else {
            showMessage(data.Message);
        }

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        console.log(textStatus);
    })
    .always(() => {
    });

}

/**
 * 削除のための確認の表示
 */
function confirmDeletion() {

    // 編集ダイアログを隠す
    $("#dlg1").modal("hide");

    // 確認ダイアログを開く
    $("#dlg2").modal("show");

}

/**
 * 削除する
 */
function deleteUser() {

    // IDを取得
    let id = $("#dlg1 .dlg1-id").val();

    // APIに投げる
    $.ajax({
        url: '/s/users/api/delete',
        type: 'POST',
        dataType: 'json',
        data: { Id: id }
    })
    .done((data) => {

        // 行を消す
        if (data.Result) {
            let row = $("#ji-tbl-main #row-" + data.Id);
            row.remove();
            $("#dlg1").modal("hide");
        }

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        console.log(textStatus);
    })
    .always(() => {
    });

}

/**
 * 読み込み時
 */
$(window).on("load", (e) => {

    for (let data of initData) {
        showOnList(data);
    }

    // イベントの登録
    $("#ji-btn-update").on("click", updateUser);
    $("#ji-btn-delete").on("click", confirmDeletion);
    $("#dlg2-btn-yes").on("click", (e) => { $("#dlg2").modal("hide"); $("#dlg1").modal("show"); deleteUser() });
    $("#dlg2-btn-no").on("click", (e) => { $("#dlg2").modal("hide"); $("#dlg1").modal("show"); });
    $(".cell-btn-detail").on("click", openEditDialog);

});