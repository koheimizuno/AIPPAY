/**
 * 一覧上に権利の情報を表示する
 */
function showOnList(data, fullItems) {

    // 更新対象の行を取得する
    let tbl = $("#ji-tbl-main tbody");
    let row = tbl.find("#row-" + data.Id);

    // 表示
    row.find(".cell-subject").text(data.Subject ?? "");
    row.find(".cell-next-limit").text(data.NextProcedureLimit_Date ?? "");
    row.find(".cell-expire-date").text(data.ExpirationDate_Date ?? "")

    // 権利者のセット
    let holderNames = [];
    if (data.Holders) {
        for (let h of data.Holders) {
            if (h.Name !== undefined) {
                holderNames.push(h.Name);
            }
        }
    }
    row.find(".cell-holders").text(holderNames.length > 0 ? holderNames.join(", ") : "");
    
    // 特許庁DB以外の項目
    if (fullItems) {

        row.find(".cell-country").text(data.CountryDescription ?? "");
        row.find(".cell-law").text(data.LawName ?? "");
        row.find(".cell-reg-num").text(data.RegistrationNumber ?? "");
        if (data.UserOrganization) {
            row.find(".cell-user-org").text(data.UserOrganization);
            row.find(".cell-user-org").removeClass("d-none");
        } else {
            row.find(".cell-user-org").addClass("d-none");
        }
        row.find(".cell-user-name").text(data.UserName ?? "");
    
    }
}

/**
 * 編集ダイアログ上の情報を最新にする
 */
function showOnDialog(data, fullItems) {

    // ダイアログ
    let dlg = $("#dlg1");

    // 出願番号
    dlg.find(".dlg1-app-num").val(data.ApplicationNumber ?? "");

    // 消滅フラグ
    if (data.Disappered === undefined) {
        dlg.find(".dlg1-disappered").prop("checked", false);
    } else {
        dlg.find(".dlg1-disappered").prop("checked", data.Disappered);
    }

    // 名称
    dlg.find(".dlg1-subject").val(data.Subject ?? "");

    // 請求項の数
    dlg.find(".dlg1-num-of-claims").val("");
    if (data.Law == "Patent") {
        dlg.find(".dlg1-num-of-claims").val(data.NumberOfClaims ?? "");
        dlg.find(".dlg1-num-of-claims-conteiner").removeClass("d-none");
    } else {
        dlg.find(".dlg1-num-of-claims-conteiner").addClass("d-none");
    }

    // 商標の区分
    dlg.find(".dlg1-classes").val("");
    if (data.Law == "Trademark") {
        if (data.Classes) {
            dlg.find(".dlg1-classes").val(data.Classes.join(","));
        }
        dlg.find(".dlg1-classes-container").removeClass("d-none");
    } else {
        dlg.find(".dlg1-classes-container").addClass("d-none");
    }

    // 防護標章フラグ
    //if (data.Country == "JP" && data.Law == "Trademark") {
    //    dlg.find(".dlg1-defensive").prop("checked", data.DefensiveMark ?? false);
    //    dlg.find(".dlg1-defensive-container").removeClass("d-none");
    //} else {
    //    dlg.find(".dlg1-defensive").prop("checked", false);
    //    dlg.find(".dlg1-defensive-container").addClass("d-none");
    //}

    // PCT番号
    dlg.find(".dlg1-pct").val(data.PctNumber ?? "");

    // 優先権番号
    dlg.find(".dlg1-prior").val("");
    if (data.PriorNumber) {
        dlg.find(".dlg1-prior").val(data.PriorNumber.join("\n"));
    }

    // 出願日
    dlg.find(".dlg1-app-date").val(data.ApplicationDate_Date ?? "");

    // 審査請求日
    dlg.find(".dlg1-exam-date").val("");
    if (data.Country == "JP" && data.Law == "Patent") {
        dlg.find(".dlg1-exam-date").val(data.ExamClaimedDate_Date ?? "");
        dlg.find(".dlg1-exam-date-container").removeClass("d-none");
    } else {
        dlg.find(".dlg1-exam-date-container").addClass("d-none");
    }

    // 登録査定日等
    dlg.find(".dlg1-reginvd-date").val("");
    dlg.find(".dlg1-rpayd-date").val("");
    dlg.find(".dlg1-npayd-date").val("");
    if (data.Country == "JP" && data.Law == "Trademark") {
        dlg.find(".dlg1-reginvd-date").val(data.RegistrationInvestigatedDate_Date ?? "");
        dlg.find(".dlg1-rpayd-date").val(data.RegistrationPaymentDate_Date ?? "");
        dlg.find(".dlg1-npayd-date").val(data.RenewPaymentDate_Date ?? "");
        dlg.find(".dlg1-reginvd-date-container").removeClass("d-none");
        dlg.find(".dlg1-rpayd-date-container").removeClass("d-none");
        dlg.find(".dlg1-npayd-date-container").removeClass("d-none");
    } else {
        dlg.find(".dlg1-reginvd-date-container").addClass("d-none");
        dlg.find(".dlg1-rpayd-date-container").addClass("d-none");
        dlg.find(".dlg1-npayd-date-container").addClass("d-none");
    }

    // 登録日
    dlg.find(".dlg1-reg-date").val(data.RegistrationDate_Date ?? "");

    // 存続期間満了日
    dlg.find(".dlg1-expir-date").val(data.ExpirationDate_Date ?? "");

    // 権利者の初期化
    let holder_elems = dlg.find(".hld_set");
    for (let i = 1; i < holder_elems.length; i++) {
        holder_elems.eq(i).remove();
    }
    holder_elems.eq(0).find(".hld_id").val("");
    holder_elems.eq(0).find(".hld_nm").val("");

    // 権利者のセット
    if (data.Holders) {
        let holder_container = $("#dlg1-hld");
        for (let i = 0; i < data.Holders.length; i++) {
            let holder_elem = holder_container.find(".hld_set").eq(0);
            if (i > 0) {
                holder_elem = holder_elem.clone(true);
                holder_container.append(holder_elem);
            }
            holder_elem.find(".hld_id").val(data.Holders[i].Id ?? "");
            holder_elem.find(".hld_nm").val(data.Holders[i].Name ?? "");
        }
    }

    // 納付済年分
    dlg.find(".dlg1-py").val("");
    dlg.find(".dlg1-py-us").val("");
    if (true) {
        dlg.find(".dlg1-py").val(data.PaidYears ?? "");
        dlg.find(".dlg1-py").removeClass("d-none");
        dlg.find(".dlg1-py-us").addClass("d-none");
    }

    // 次回期限
    dlg.find(".dlg1-next").val(data.NextProcedureLimit_Date ?? "");

    // 特許庁DBのURL
    dlg.find(".dlg1-sourceurl").val(data.SourceURL ?? "");
    dlg.find(".dlg1-sourceurl-link").text(data.SourceURL ?? "");
    dlg.find(".dlg1-sourceurl-link").attr("href", data.SourceURL ?? "");
    if (data.SourceURL) {
        dlg.find(".dlg1-sourceurl-area").removeClass("d-none");
    } else {
        dlg.find(".dlg1-sourceurl-area").addClass("d-none");
    }

    // 特許庁DB以外の項目
    if (fullItems) {

        // キーの保存
        dlg.find(".dlg1-country").val(data.Country ?? "");
        dlg.find(".dlg1-law").val(data.Law ?? "");

        // 国、法域、登録番号
        dlg.find(".dlg1-country-description").text(data.CountryDescription ?? "");
        dlg.find(".dlg1-law-name").text(data.LawName ?? "");
        dlg.find(".dlg1-reg-num").text(data.RegistrationNumber ?? "");

        // ユーザー
        dlg.find(".dlg1-user").text((data.UserOrganization ?? "") + " " + (data.UserName ?? ""));

        // 整理番号
        dlg.find(".dlg1-man-num").val(data.ManagementNumber ?? "");

        // 通知制限
        dlg.find(".dlg1-silent").prop("checked", data.Silent ?? false);

    }

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
        url: '/s/props/api/get',
        type: 'POST',
        dataType: 'json',
        data: { Id: id }
    })
    .done((data) => {

        // ダイアログ上に表示
        showOnDialog(data, true);

        // ダイアログの表示
        $("#dlg1").modal("show");

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
 * 特許庁DBの照会
 */
function referToDB() {

    // クエリーの構成
    let q = {
        Id: $("#dlg1 .dlg1-id").val()
    };

    // ローディング
    showLoadingOverlay();

    // 更新をリクエスト
    $.ajax({
        url: '/s/props/api/refer',
        type: 'POST',
        dataType: 'json',
        data: q
    })
    .done((data) => {

        // 結果の確認
        if (!data.Result) {
            // 失敗時はメッセージを表示して終了
            showMessage(data.Message);
            return;
        }

        data = data.Data;

        // 更新結果をダイアログに反映
        showOnDialog(data, false);

        // リストにも反映
        showOnList(data, false);

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        console.log(textStatus);
        $("#ed_msg").text("{{ UI.Pages.Property.CannotRefer }}");
    })
    .always(() => {
        // ローディング
        hideLoadingOverlay();
    });

}

/**
 * 権利者欄を増やす
 */
function addHolderField() {

    let dlg = $("#dlg1");
    let container = dlg.find("#dlg1-hld");
    let elem = container.find(".hld_set").eq(0);
    elem = elem.clone(true);
    elem.find(".hld_id").val("");
    elem.find(".hld_nm").val("");
    container.append(elem);

}

/**
 * 権利者欄を削除する
 */
function removeHolderField(e) {

    // 権利者フィールドの数を調べる
    let dlg = $("#dlg1");
    let container = dlg.find("#dlg1-hld");
    let elem = container.find(".hld_set");

    // 1つならフィールドをクリアーして終わり
    if (elem.length < 2) {

        elem.find(".hld_id").val("");
        elem.find(".hld_nm").val("");
        return;

    }

    // クリックされたボタンのあるフィールドを削除
    $(e.currentTarget).parents(".hld_set").remove();

}

/**
 * 更新する
 */
function updateProperty() {

    let p = {};
    let v = null;

    // IDを取得
    p.Id = $("#dlg1 .dlg1-id").val();

    // 編集ダイアログから値を収集する
    let dlg = $("#dlg1");

    // 出願番号
    v = dlg.find(".dlg1-app-num").val();
    if (v) p.ApplicationNumber = v;

    // 消滅フラグ
    if (dlg.find(".dlg1-disappered").prop("checked")) p.Disappered = 1;

    // 名称
    v = dlg.find(".dlg1-subject").val();
    if (v) p.Subject = v;

    // 請求項の数
    v = dlg.find(".dlg1-num-of-claims").val();
    if (v) {
        p.NumberOfClaims = parseInt(v);
    }

    // 商標の区分
    v = dlg.find(".dlg1-classes").val();
    if (v) p.Classes = v;

    // 防護標章フラグ
    if (dlg.find(".dlg1-devensive").prop("checked")) {
        p.DefensiveMark = true;
    }

    // 整理番号
    v = dlg.find(".dlg1-man-num").val();
    if (v) p.ManagementNumber = v;

    // PCT番号
    v = dlg.find(".dlg1-pct").val();
    if (v) p.PctNumber = v;

    // 優先権番号
    v = dlg.find(".dlg1-prior").val();
    if (v) {
        p.PriorNumber = v.split("\n").join("\t");
    }

    // 出願日
    v = dlg.find(".dlg1-app-date").val();
    if (v) p.ApplicationDate = v;

    // 審査請求日
    v = dlg.find(".dlg1-exam-date").val();
    if (v) p.ExamClaimedDate = v;
    v = dlg.find(".dlg1-reginvd-date").val();
    if (v) p.RegistrationInvestigatedDate = v;
    v = dlg.find(".dlg1-rpayd-date").val();
    if (v) p.RegistrationPaymentDate = v;
    v = dlg.find(".dlg1-npayd-date").val();
    if (v) p.RenewPaymentDate = v;

    // 登録日
    v = dlg.find(".dlg1-reg-date").val();
    if (v) p.RegistrationDate = v;

    // 存続期間満了日
    v = dlg.find(".dlg1-expir-date").val();
    if (v) p.ExpirationDate = v;

    // 権利者
    let holder_elems = $("#dlg1-hld .hld_set");
    let holder_cnt = 0;
    for (let i = 0; i < holder_elems.length; i++) {
        let holder_elem = holder_elems.eq(i);
        v = holder_elem.find(".hld_nm").val();
        if (v) {
            p['Holder_Name_' + holder_cnt] = v;
            v = holder_elem.find(".hld_id").val();
            if (v) {
                p['Holder_Id_' + holder_cnt] = v;
            }
            holder_cnt++;
        }
    }

    // 納付済年分
    v = dlg.find(".dlg1-py").val();
    if (v) {
        p.PaidYears = v;
    } else {
        v = dlg.find(".dlg1-py-us").val();
        if (v) p.PaidYears = v;
    }

    // 次回期限
    v = dlg.find(".dlg1-next").val();
    if (v) p.NextProcedureLimit = v;

    // 通知制限
    p.Silent = dlg.find(".dlg1-silent").prop("checked");

    // 特許庁DBのURL
    v = $(".dlg1-sourceurl").val();
    if (v && v !== "") {
        p.SourceURL = v;
    }

    // APIに投げる
    $.ajax({
        url: '/s/props/api/update',
        type: 'POST',
        dataType: 'json',
        data: p
    })
    .done((data) => {

        if (data.Result) {
            // 更新結果で画面を更新する
            showOnDialog(data, true);
            showOnList(data, true);
            // 編集ダイアログを一旦閉じる
            $("#dlg1").modal("hide");
        } else {
            showMessage(data.Message ?? "ERROR");
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

    // 編集ダイアログを一旦閉じる
    $("#dlg1").modal("hide");

    // 確認ダイアログを開く
    $("#dlg2").modal("show");

}

/**
 * 削除する
 */
function deleteProperty() {

    // 確認ダイアログを閉じる
    $("#dlg2").modal("hide");

    // IDを取得
    let id = $("#dlg1 .dlg1-id").val();

    // APIに投げる
    $.ajax({
        url: '/s/props/api/delete',
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

    // イベントの登録
    $("#ji-btn-update").on("click", updateProperty);
    $("#ji-btn-delete").on("click", confirmDeletion);
    $("#dlg2-btn-yes").on("click", (e) => { $("#dlg2").modal("hide"); $("#dlg1").modal("show"); deleteProperty(); });
    $("#dlg2-btn-no").on("click", (e) => { $("#dlg2").modal("hide"); $("#dlg1").modal("show"); });
    $(".cell-btn-detail").on("click", openEditDialog);
    $(".hld_rm").on("click", removeHolderField);
    $("#hld_ad").on("click", addHolderField);
    $("#btn-jpp").on("click", (e) => { referToDB(); });

    // 情報をリストに表示する
    for (let data of initData) {
        showOnList(data, true);
    }

});