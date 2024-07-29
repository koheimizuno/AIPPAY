/**
 * 検索条件の適用
 */
function applyQuery(e) {
    $("#q_q").val($("#sc_qry").val());
    $("#q_s").val($("#st").val());
    $("#q")[0].submit();
}

/**
* 編集ダイアログの初期化
*/
function initEditForm() {
    $(".required").removeClass("d-none");
    $("#ed_id").val("");
    $("#ed_cnt").val("JP");
    $("#ed_cnt").prop("disabled", false);
    $("#ed_cnt_unk").val("");
    $("#ed_cnt_unk").addClass("d-none");
    $("#ed_cnt_unk").prop("placeholder", "");
    $("#ed_law_Patent").prop("checked", true);
    $("input[name='ed_law']").prop("disabled", false);
    $("#ed_regn").prop("disabled", false);
    $("#ed_appn").prop("disabled", false);
    $(".ed_txt").val("");
    $("#ed_sourceurl_link").text("");
    $("#ed_sourceurl_link").attr("href", "");
    $("#ed_sourceurl_area").addClass("d-none");
    let e = $(".ed_hld_set");
    for (let i = 0; i < e.length; i++) {
        if (i == 0) continue;
        e.eq(i).remove();
    }
    $(".ed_hld_id").val("");
    $(".ed_hld_nm").val("");
    $("#ed_dft").prop("checked", false);

    // 納付済年分の値域設定
    $("#ed_py").prop("min", "1");
    $("#ed_py").prop("max", false);
    $("#ed_py").prop("step", "1");
    $("#ed_py").val("");
    $("#ed_py_us").val("");

    // 登録・削除ボタンの制御
    $("#ed_reg_btn").prop("disabled", false);
    $("#ed_del_btn").prop("disabled", false);

    // 法区分が変わったことにして各項目の表示を制御させる
    onValueChangedOnEditForm(null);

    // 警告メッセージの初期化
    $("#ed_msg").text("");
}

/**
 * 日付を文字列に合わせる
 */
function formatDate(text) {

    if (!text) return null;

    // 日付を抽出
    let m = text.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
    let v1 = parseInt(m[1]).toString();
    let v2 = parseInt(m[2]).toString();
    let v3 = parseInt(m[3]).toString();

    if ("{{ UI.Language.Selected }}" == "ja") {
        return `${v1}年${v2}月${v3}日`;
    } else {
        v1 = v1.padStart(4, "0");
        v2 = v2.padStart(2, "0");
        v3 = v3.padStart(2, "0");
        return `${v1}-${v2}-${v3}`;
    }

}

/**
 * 日付を文字列に合わせる(HTML)
 */
function formatDateHtml(text) {

    if (!text) return null;

    // 日付を抽出
    let m = text.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
    let v1 = parseInt(m[1]).toString();
    let v2 = parseInt(m[2]).toString();
    let v3 = parseInt(m[3]).toString();

    if ("{{ UI.Language.Selected }}" == "ja") {
        return `<span class="date">${v1}<span class="date-sep">年</span>${v2}<span class="date-sep">月</span>${v3}<span class="date-sep">日</span></span>`;
    } else {
        v1 = v1.padStart(4, "0");
        v2 = v2.padStart(2, "0");
        v3 = v3.padStart(2, "0");
        return `<span class="date">${v1}<span class="date-sep">-</span>${v2}<span class="date-sep">-</span>${v3}</span>`;
    }

}

/**
 * 権利の情報を一覧上に表示する
 */
function showPropInfo(id, data) {

    let tbl = $("#tbl-props > tbody");
    let row = tbl.find("#tr_" + id);
    let isNew = false;

    if (!row || row.length == 0) {
        // 新規
        row = tbl.find("tr").eq(0);
        if (row.attr("id")) {
            row = row.clone(true);
            isNew = true;
        }
    }

    // 行ID
    row.attr("id", "tr_" + data.Id);

    // 法域
    row.find(".cell-law").text(data.LawName ?? "");
    ["Patent", "Utility", "Design", "Trademark"].forEach((x) => {
        row.removeClass("tr_" + x);
    });
    row.addClass("tr_" + data.Law);

    // 登録番号
    row.find(".cell-reg-num").text(data.RegistrationNumber ?? "");

    // 整理番号
    row.find(".cell-management-num").text(data.ManagementNumber ?? "");

    // 国
    row.find(".cell-country").text(data.CountryDescription ?? "");

    // PCT番号
    let elem = row.find(".cell-pct .pct");
    if (data.PctNumber) {
        elem.removeClass("d-none");
        elem.text(data.PctNumber);
    } else {
        elem.addClass("d-none");
        elem.text("");
    }

    // 優先番号
    elem = row.find(".cell-pct .prior");
    if (data.PriorNumber && data.PriorNumber.length > 0) {
        elem.removeClass("d-none");
        elem.text(data.PriorNumber[0] + (data.PriorNumber.length > 1 ? "{{ UI.Vocabulary.More }}" : ""));
    } else {
        elem.addClass("d-none");
        elem.text("");
    }

    // 権利者
    row.find(".cell-holder").text(data.HolderNames ?? "");

    // 名称
    row.find(".cell-subject").text(data.Subject ?? "");

    // 存続期間満了日
    elem = row.find(".cell-expiration");
    elem.empty();
    if (data.ExpirationDate) {
        elem.append($(formatDateHtml(data.ExpirationDate)));
    }

    // 次回期限
    elem = row.find(".cell-limit .limitdate");
    elem.empty();
    if (data.NextProcedureLimit2) {
        elem.append($(formatDateHtml(data.NextProcedureLimit2)));
    } else if (data.NextProcedureLimit) {
        elem.append($(formatDateHtml(data.NextProcedureLimit)));
    }
    if (data.AdditionalPeriod) {
        row.find(".cell-limit .additional").removeClass("d-none");
    } else {
        row.find(".cell-limit .additional").addClass("d-none");
    }
    if (data.Hurry) {
        row.find(".cell-limit .hurry").removeClass("d-none");
    } else {
        row.find(".cell-limit .hurry").addClass("d-none");
    }

    // 次回の年分
    if (data.YearForPay) {
        row.find(".cell-year").text(data.YearForPay);
    } else {
        row.find(".cell-year").text("");
    }

    // 次回料金
    let fee1 = row.find(".cell-fee .fee-orig");
    let fee2 = row.find(".cell-fee .fee-ex");
    if (data.NextOfficialFee) {
        fee1.find(".price").text(data.NextOfficialFee);
        fee1.find(".currency-unit").text(data.CurrencyLocal);
        if (data.ExchangedCurrencyLocal && data.ExchangedCurrencyLocal != data.CurrencyLocal) {
            fee2.find(".price").text(data.NextOfficialFee_Exchanged);
            fee2.find(".currency-unit").text(data.ExchangedCurrencyLocal);
            fee2.removeClass("d-none");
        } else {
            fee2.find(".price").text("");
            fee2.find(".currency-unit").text("");
            fee2.addClass("d-none");
        }
    } else {
        row.find(".cell-fee .price").text("");
        row.find(".cell-fee .currency-unit").text("");
        fee2.addClass("d-none");
    }

    // すべてのボタンのvalueにidを設定
    row.find("button").val(data.Id);

    // 依頼（候補追加）の可否制御
    let btn = row.find(".cartBtn");
    let msg = row.find(".p-cannot-cart");
    if (data.Requestable) {
        btn.removeClass("d-none");
        btn.prop("disabled", false);
        msg.text("");
        msg.attr("title", "");
        msg.addClass("d-none");
    } else {
        btn.addClass("d-none");
        btn.prop("disabled", true);
        msg.text(data.RequestWarning_Short ?? "");
        msg.attr("title", data.RequestWarning ?? "");
        msg.removeClass("d-none");
    }

    // 新規の場合はテーブルに追加
    if (isNew) {
        tbl.append(row);
    }

}

/**
 * 一覧から権利を消す
 */
function removePropFromTable(id) {

    let tbl = $("#tbl-props > tbody");
    let row = tbl.find("#tr_" + id);
    if (row.length > 0) row.remove();

}

/**
 * 編集フォームでの値の変更を監視
 */
function onValueChangedOnEditForm(e) {

    // 登録ボタンを無効化
    $("#ed_reg_btn").prop("disabled", true);

    // 必須マークを一旦非表示に
    $("span.required").addClass("d-none");

    // 国・地域が未選択
    $("label[for='ed_cnt'] span.required").removeClass("d-none");
    if ($("#ed_cnt").val()) {
        if ($("#ed_cnt").val() == "UNK" && !$("#ed_cnt_unk").val()) {
            $("#ed_msg").text("{{ UI.Error.E00010 }}");
            return;
        }
    } else {
        $("#ed_msg").text("{{ UI.Error.E00010 }}");
        return;
    }

    // 法域が未選択
    $("label[for='ed_law'] span.required").removeClass("d-none");
    if ($("input[name='ed_law']:checked").length == 0) {
        $("#ed_msg").text("{{ UI.Error.E00020 }}");
        return;
    }

    // 国と法区分の取得
    let cnt = $("#ed_cnt").val();
    let law = $("input[name='ed_law']:checked").val();

    if (true) {
        $("label[for='ed_law_Utility']").removeClass("d-none");
        $("label[for='ed_law_Design']").removeClass("d-none");
    }

    // 納付済年分の値域設定
    if (true) {
        $(".var-form-py").removeClass("d-none");
        $(".var-form-py_us").addClass("d-none");
    }

    if (cnt == 'JP' && law == 'Trademark') {
        $("#ed_py").prop("min", "5");
        $("#ed_py").prop("max", "10");
        $("#ed_py").prop("step", "5");
    } else {
        $("#ed_py").prop("step", "1");
        $("#ed_py").prop("max", false);
        if (cnt == 'JP') {
            $("#ed_py").prop("min", "3");
        } else {
            $("#ed_py").prop("min", "1");
        }
    }

    // PCT番号欄の切り替え
    if (law == "Patent" || law == "Utility") {
        $(".var-form-pct").removeClass("d-none");
    } else {
        $(".var-form-pct").addClass("d-none");
    }

    // 優先番号欄は常に表示
    $(".var-form-pri").removeClass("d-none");

    // 審査請求日の切り替え
    if (cnt == "JP" && law == "Patent") {
        $(".var-form-exmd").removeClass("d-none");
    } else {
        $(".var-form-exmd").addClass("d-none");
    }

    // 日付項目
    if (cnt == 'JP' && law == 'Trademark') {
        $(".var-form-reginvd").removeClass("d-none");
        $(".var-form-rpayd").removeClass("d-none");
        $(".var-form-npayd").removeClass("d-none");
    } else {
        $(".var-form-reginvd").addClass("d-none");
        $(".var-form-rpayd").addClass("d-none");
        $(".var-form-npayd").addClass("d-none");
    }

    // 請求項の数の切り替え
    if ((law == "Patent" || law == "Utility")) {
        $(".var-form-clms").removeClass("d-none");
    } else {
        $(".var-form-clms").addClass("d-none");
    }

    // 区分の切り替え
    if (law == "Trademark") {
        $(".var-form-clss").removeClass("d-none");
    } else {
        $(".var-form-clss").addClass("d-none");
    }

    // 防護標章の切り替え
    //if (cnt == "JP" && law == "Trademark") {
    //    $(".var-form-dft").removeClass("d-none");
    //} else {
    //    $(".var-form-dft").addClass("d-none");
    //}

    // 識別番号
    $(".ed_hld_id").removeClass("d-none");

    // DB照会の可否切り替え
    if ((cnt == "JP") && ($("#ed_regn").val() || $("#ed_appn").val())) {
        $("#ed_refer").prop("disabled", false);
    } else {
        $("#ed_refer").prop("disabled", true);
    }

    // 登録番号が未入力
    $("label[for='ed_regn'] span.required").removeClass("d-none");
    if (!$("#ed_regn").val()) {
        $("#ed_msg").text("{{ UI.Error.E00030 }}");
        return;
    }

    // 登録ボタンを有効化
    let id = $("#ed_id").val();
    if (id && id !== "") {
        $("#ed_reg_btn").prop("disabled", false);
    } else if ($("#ed_refered").val() == "1") {
        $("#ed_reg_btn").prop("disabled", false);
    }

}

/**
 * 詳細ボタンのクリックイベント
 */
function onEditButtonClicked(e) {

    let btn = $(e.currentTarget);
    let q = { _csrf: csrfToken };
    q.id = btn.val();

    // 現在の登録内容の取得
    $.ajax({
        url: '/props/api/detail', type: 'POST', dataType: 'json',
        data: q
    })
        .done(data => {

            // 取得失敗の場合はダイアログを開かない
            if (!data.Result) {
                return;
            }

            // ダイアログの初期化
            initEditForm();

            $("#ed_id").val(data.Id);
            $("#ed_cnt").val(data.Country);
            $("#ed_cnt").prop("disabled", true);
            if (data.Country == 'UNK') {
                $("#ed_cnt_unk").val(data.CountryDescription);
            }

            $("#ed_cnt_unk").addClass("d-none");
            $("#ed_cnt_unk").prop("placeholder", "");
            $("#ed_law_" + data.Law).prop("checked", true);
            $("input[name='ed_law']").prop("disabled", true);
            $("#ed_regn").val(data.RegistrationNumber);
            $("#ed_regn").prop("disabled", true);
            $("#ed_appn").val(data.ApplicationNumber);
            $("#ed_appn").prop("disabled", true);
            $("#ed_sjt").val(data.Subject);
            if (data.PctNumber) $("#ed_pct").val(data.PctNumber);
            if (data.PriorNumber) $("#ed_pri").val(data.PriorNumber.join("\n"));
            if (data.NextProcedureLimit) $("#ed_procd").val(data.NextProcedureLimit);
            if (data.ApplicationDate) $("#ed_appd").val(data.ApplicationDate);
            if (data.ExamClaimedDate) $("#ed_exmd").val(data.ExamClaimedDate);
            if (data.RegistrationDate) $("#ed_regd").val(data.RegistrationDate);
            if (data.ExpirationDate) $("#ed_expd").val(data.ExpirationDate);
            if (data.RegistrationInvestigatedDate) $("#ed_reginvd").val(data.RegistrationInvestigatedDate);
            if (data.RegistrationPaymentDate) $("#ed_rpayd").val(data.RegistrationPaymentDate);
            if (data.RenewPaymentDate) $("#ed_npayd").val(data.RenewPaymentDate);
            if (data.NumberOfClaims) $("#ed_clms").val(data.NumberOfClaims);
            if (data.Classes) $("#ed_clss").val(data.Classes);
            if (true) {
                if (data.PaidYears) $("#ed_py").val(data.PaidYears);
            }
            if (data.ManagementNumber) $("#ed_mgtn").val(data.ManagementNumber);
            if (data.Holders) {
                for (let i = 0; i < data.Holders.length; i++) {
                    let n = $(".ed_hld_set");
                    if (i > 0) {
                        n = n.eq(0).clone(true);
                        n.find(".ed_hld_id").val("");
                        n.find(".ed_hld_nm").val("");
                        n.insertBefore("#ed_hld_adp");
                    }
                    if (data.Holders[i].Id) {
                        n.find(".ed_hld_id").val(data.Holders[i].Id);
                    }
                    if (data.Holders[i].Name) {
                        n.find(".ed_hld_nm").val(data.Holders[i].Name);
                    }
                }
            }
            $("#ed_dft").prop("checked", data.Defensive ?? false);
            $("#ed_silent").prop("checked", data.Silent ?? false);

            // 依頼（カート追加）不可理由の表示
            if (data.RequestWarning) {
                $("#ed_msg").text(data.RequestWarning);
            }

            // 処理中の場合は更新を不可とする
            if (data.UnderProcess) {
                $("#ed_reg_btn").prop("disabled", true);
                $("#ed_del_btn").prop("disabled", true);
            }

            // 固定リンク
            $("#ed_sourceurl").val(data.SourceURL ?? "");
            $("#ed_sourceurl_link").text(data.SourceURL ?? "");
            $("#ed_sourceurl_link").attr("href", data.SourceURL ?? "");
            if (data.SourceURL) {
                $("#ed_sourceurl_area").removeClass("d-none");
            } else {
                $("#ed_sourceurl_area").addClass("d-none");
            }

            $("#editDialog").modal({ show: true, backdrop: "static" });
            onValueChangedOnEditForm(null);

        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
        });
}

/**
 * 放棄ボタンのクリックイベント
 */
function onAbandonButtonClicked(e) {
    // 確認ダイアログを開く
    let id = $(e.currentTarget).val();
    $("#dlg-abandon-id").val(id);
    $("#dlg-abandon-msg").text("");
    $("#dlg-abandon").modal("show");
}


/**
 * ダイアログでのメッセージの表示
 */
function showMessage(message) {
    $("#dlgGenMsg").text(message);
    $("#dlgGen").modal("show");
}

/**
 * カートに入っている権利の数を取得する
 */
function checkCart() {
    $.ajax({
        url: '/props/api/cart', type: 'POST', dataType: 'json',
        data: { _csrf: csrfToken }
    })
        .done(data => {
            if (data.count > 0) {
                $("#navCart").removeClass("d-none");
                $("#cartCount").text(data.count);
            } else {
                $("#navCart").addClass("d-none");
            }
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
            $("#navCart").addClass("d-none");
        });
}

/**
* 候補追加ボタンのクリックイベント
*/
function onCartButtonClicked(e) {
    let btn = $(e.currentTarget);
    $.ajax({
        url: '/props/api/req', type: 'POST', dataType: 'json',
        data: { id: btn.val(), _csrf: csrfToken }
    })
        .done((data) => {
            if (!data.result) {
                return;
            }
            btn.addClass("d-none");
            btn.parent().find(".cartMsg").removeClass("d-none");
            checkCart();
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
        });
}

/**
 * 編集フォームでの編集（更新）を確定させる
 */
function submitForUpdate() {

    // ボタンの無効化（二重処理防止）
    $("#ed_reg_btn").prop("disabled", true);

    // メッセージの初期化
    $("#ed_msg").text("");

    // クエリーの構築
    let v;
    let q = { _csrf: csrfToken };
    let id = $("#ed_id").val();
    if (id && id != "") q.Id = id;
    q.Country = $("#ed_cnt").val();
    if (q.Country == 'UNK') {
        v = $("#ed_cnt_unk").val();
        q.CountryDescription = v;
    }
    q.Law = $("input[name='ed_law']:checked").val();
    q.RegistrationNumber = $("#ed_regn").val();
    q.ApplicationNumber = $("#ed_appn").val();
    v = $("#ed_sjt").val();
    if (v) q.Subject = v;
    v = $("#ed_mgtn").val();
    if (v) q.ManagementNumber = v;
    v = $("#ed_pct").val();
    if (v) q.PctNumber = v;
    v = $("#ed_pri").val();
    if (v) q.PriorNumber = v;
    v = $("#ed_procd").val();
    if (v) q.NextProcedureLimit = v;
    v = $("#ed_appd").val();
    if (v) q.ApplicationDate = v;
    v = $("#ed_exmd").val();
    if (v) q.ExamClaimedDate = v;
    v = $("#ed_regd").val();
    if (v) q.RegistrationDate = v;
    v = $("#ed_expd").val();
    if (v) q.ExpirationDate = v;
    v = $("#ed_reginvd").val();
    if (v) q.RegistrationInvestigatedDate = v;
    v = $("#ed_rpayd").val();
    if (v) q.RegistrationPaymentDate = v;
    v = $("#ed_npayd").val();
    if (v) q.RenewPaymentDate = v;
    v = $("#ed_clms").val();
    if (v) q.NumberOfClaims = v;
    v = $("#ed_clss").val();
    if (v) q.Classes = v;
    v = $("#ed_py").val();
    if (v || v === "0") q.PaidYears = v;
    let hlds = $(".ed_hld_set");
    for (let i = 0; i < hlds.length; i++) {
        let hld = hlds.eq(i);
        let obj = {};
        v = hld.find(".ed_hld_id").val();
        if (v) obj.Id = v;
        v = hld.find(".ed_hld_nm").val();
        if (v) obj.Name = v;
        if (obj.Id || obj.Name) {
            if (!q.Holders) q.Holders = [];
            q.Holders.push(obj);
        }
    }
    if (q.Holders) q.Holders = JSON.stringify(q.Holders);
    if ($("#ed_dft").prop("checked")) {
        q.Defensive = 1;
    }
    q.Silent = $("#ed_silent").prop("checked") ? 1 : 0;

    v = $("#ed_sourceurl").val();
    if (v && v !== "") {
        q.SourceURL = v;
    }

    // Idが指定されている場合（更新の場合）整理番号と通知制限のみ送る
    if (q.Id) {
        let x = { Id: q.Id };
        if (q.ManagementNumber) {
            x.ManagementNumber = q.ManagementNumber;
        }
        if (q.Silent) {
            x.Silent = q.Silent;
        }
        q = x;
    }

    console.log(q);

    // ローディング表示
    showLoadingOverlay();

    // 更新をリクエスト
    $.ajax({
        url: '/props/api/update', type: 'POST', dataType: 'json',
        data: q
    })
        .done(data => {

            // 結果の確認
            if (!data.Result) {
                $("#ed_msg").text(data.Message);
                return;
            }

            // 登録結果の再表示
            showPropInfo(data.Id, data);

            // 編集画面を隠す
            $("#editDialog").modal("hide");

        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
            $("#ed_msg").text("{{ UI.Pages.Property.CannotRegister }}");
        })
        .always(() => {
            // ローディング表示の削除
            hideLoadingOverlay();
        });

}

/**
 * 追納情報の表示
 */
function notifyAdditionalPeriod(e) {
    showMessage("{{ UI.Pages.Property.AdditionalComment }}");
}

/**
 * 主要キー項目に変更があったとき
 */
function onKeysChanged(e) {
    let id = $("#ed_id").val();
    if (id && id !== "") {
        // 既存の登録の場合は無視
    } else {
        // 特許庁DB照会をするまで登録できない
        $("#ed_refer").prop("disabled", true);
    }
}

/**
 * ページが読み込まれたとき
 */
$(window).on("load", e => {

    // 追加ボタン（編集ダイアログの表示）
    $("button#addButton").on("click", e => {
        initEditForm();
        $("#ed_del_btn").prop("disabled", true);
        $("#ed_reg_btn").prop("disabled", true);
        $("#editDialog").modal({ show: true, backdrop: "static" });
    });

    // 国の変更
    $("#ed_cnt").on("change", e => {
        if ($("#ed_cnt").val() == "UNK") {
            $("#ed_cnt_unk").removeClass("d-none");
            $("#ed_cnt_unk").prop("placeholder", "{{ UI.Pages.Property.Hint.CountryDescription }}");
        } else {
            $("#ed_cnt_unk").addClass("d-none");
            $("#ed_cnt_unk").prop("placeholder", "");
            $("#ed_cnt_unk").val("");
        }
    });

    // 主要キー項目の変更
    $("#ed_cnt").on("change", onKeysChanged);
    $("#ed_regn").on("change", onKeysChanged);
    $("#ed_law_Patent").on("change", onKeysChanged);
    $("#ed_law_Design").on("change", onKeysChanged);
    $("#ed_law_Utility").on("change", onKeysChanged);
    $("#ed_law_Trademark").on("change", onKeysChanged);

    // 明細ごとの各種ボタンの制御の追加
    $(".editBtn").on("click", onEditButtonClicked);
    $(".cartBtn").on("click", onCartButtonClicked);
    $(".btn-abandon").on("click", onAbandonButtonClicked);

    // 編集ダイアログ上のすべての編集項目にイベントを設定
    $("#editDialog input").on("change", (e) => { $("#ed_msg").text(""); onValueChangedOnEditForm(e); });
    $("#editDialog textarea").on("change", (e) => { $("#ed_msg").text(""); onValueChangedOnEditForm(e); });
    $("#editDialog select").on("change", (e) => { $("#ed_msg").text(""); onValueChangedOnEditForm(e); });

    // 削除ボタンのイベントハンドラーを登録
    $("#ed_del_btn").on("click", e => {

        // メッセージの初期化
        $("#ed_msg").text("");

        // クエリーの構築
        let q = { _csrf: csrfToken };
        let id = $("#ed_id").val();
        if (id && id != "") q.id = id;

        if (!window.confirm("{{ UI.Pages.Property.DeleteConfirmMessage }}")) {
            return;
        }

        // ローディング
        showLoadingOverlay();

        // 更新をリクエスト
        $.ajax({
            url: '/props/api/delete',
            type: 'POST',
            dataType: 'json',
            data: q
        })
            .done(data => {

                if (data.result) {
                    // テーブルから該当行を削除
                    removePropFromTable(data.id);
                    $("#editDialog").modal("hide");
                } else {
                    $("#ed_msg").text(data.message);
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
                // ローディング表示の削除
                hideLoadingOverlay();
            });

    });

    // 登録ボタンのイベントハンドラーを登録
    $("#ed_reg_btn").on("click", e => { submitForUpdate(); });

    // 権利者削除
    $(".ed_hld_rm").on("click", e => {
        let btn = $(e.currentTarget);
        let p = btn.parent();
        let sets = $(".ed_hld_set");
        if (sets.length > 1) {
            p.remove();
        } else {
            p.find(".ed_hld_id").val("");
            p.find(".ed_hld_nm").val("");
        }
    });

    // 権利者追加
    $("#ed_hld_ad").on("click", e => {
        let p = $("#ed_hld");
        let c = p.find(".ed_hld_set").eq(-1).clone(true);
        c.find(".ed_hld_id").val("");
        c.find(".ed_hld_nm").val("");
        c.insertBefore("#ed_hld_adp");
    });

    // 特許庁DBの参照
    $("#ed_refer").on("click", (e) => {

        // メッセージの初期化
        $("#ed_msg").text("");
        $("#ed_refered").val("");

        // キーの取得
        let id = $("#ed_id").val();
        let cnt = $("#ed_cnt").val();
        let law = $("input[name='ed_law']:checked").val();
        let regn = $("#ed_regn").val();
        let appn = $("#ed_appn").val();

        if (id == "" && regn == "" && appn == "") {
            $("#ed_msg").text("{{ UI.Pages.Property.InputRegistrationOrApplicationNumber }}");
            return;
        }

        // ローディング表示
        showLoadingOverlay();

        // クエリーの構成
        let q = {
            Country: cnt,
            Law: law,
        };
        if (id && id != "") { q.Id = id; }
        else if (regn && regn != "") { q.RegistrationNumber = regn; }
        else { q.ApplicationNumber = appn; }

        // 照会をリクエスト
        $.ajax({
            url: '/props/api/refer', type: 'POST', dataType: 'json',
            data: q
        })
            .done(data => {

                // 結果の確認
                if (!data.Result) {
                    // 失敗時はメッセージを表示して終了
                    $("#ed_msg").text(data.Message);
                    return;
                }

                $("#ed_regn").val(data.Data.RegistrationNumber);
                $("#ed_regn").prop("disabled", true);
                $("#ed_appn").val(data.Data.ApplicationNumber);
                $("#ed_appn").prop("disabled", true);
                $("#ed_cnt").prop("disabled", true);
                $("input[name='ed_law']").prop("disabled", true);
                $("#ed_sjt").val(data.Data.Subject);
                if (data.Data.PctNumber) $("#ed_pct").val(data.Data.PctNumber);
                if (data.Data.PriorNumber) $("#ed_pri").val(data.Data.PriorNumber.join("\n"));
                if (data.Data.NextProcedureLimit_Date) $("#ed_procd").val(data.Data.NextProcedureLimit_Date);
                if (data.Data.ApplicationDate_Date) $("#ed_appd").val(data.Data.ApplicationDate_Date);
                if (data.Data.ExamClaimedDate_Date) $("#ed_exmd").val(data.Data.ExamClaimedDate_Date);
                if (data.Data.RegistrationDate_Date) $("#ed_regd").val(data.Data.RegistrationDate_Date);
                if (data.Data.ExpirationDate_Date) $("#ed_expd").val(data.Data.ExpirationDate_Date);
                if (data.Data.RegistrationInvestigatedDate_Date) $("#ed_reginvd").val(data.Data.RegistrationInvestigatedDate_Date);
                if (data.Data.RegistrationPaymentDate_Date) $("#ed_rpayd").val(data.Data.RegistrationPaymentDate_Date);
                if (data.Data.RenewPaymentDate_Date) $("#ed_npayd").val(data.Data.RenewPaymentDate_Date);
                if (data.Data.NumberOfClaims) $("#ed_clms").val(data.Data.NumberOfClaims);
                if (data.Data.Classes) $("#ed_clss").val(data.Data.Classes);
                if (data.Data.PaidYears) $("#ed_py").val(data.Data.PaidYears);
                if (data.Data.ManagementNumber) $("#ed_mgtn").val(data.Data.ManagementNumber);
                if (data.Data.Holders) {
                    for (let i = 0; i < data.Data.Holders.length; i++) {
                        let n = $(".ed_hld_set");
                        if (i > 0) {
                            n = n.eq(0).clone(true);
                            n.find(".ed_hld_id").val("");
                            n.find(".ed_hld_nm").val("");
                            n.insertBefore("#ed_hld_adp");
                        }
                        if (data.Data.Holders[i].Id) {
                            n.find(".ed_hld_id").val(data.Data.Holders[i].Id);
                        }
                        if (data.Data.Holders[i].Name) {
                            n.find(".ed_hld_nm").val(data.Data.Holders[i].Name);
                        }
                    }
                }
                $("#ed_dft").prop("checked", data.Data.Defensive);

                // 依頼（カート追加）不可理由の表示
                if (data.RequestWarning) {
                    $("#ed_msg").text(data.RequestWarning);
                }

                // 新規の場合は取得した情報で登録可能
                if (id == "") {
                    $("#ed_cdata").val(data.cdata);
                    $("#ed_reg_btn").prop("disabled", false);
                } else {
                    $("#ed_cdata").val("");
                }

                // 固定リンク
                $("#ed_sourceurl").val(data.Data.SourceURL ?? "");
                $("#ed_sourceurl_link").text(data.Data.SourceURL ?? "");
                $("#ed_sourceurl_link").attr("href", data.Data.SourceURL ?? "");
                if (data.Data.SourceURL) {
                    $("#ed_sourceurl_area").removeClass("d-none");
                } else {
                    $("#ed_sourceurl_area").addClass("d-none");
                }

                // 照会済みをマーク
                $("#ed_refered").val("1");

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
                // ローディング表示の削除
                hideLoadingOverlay();
            });

    });

    // 検索ボタン
    $("#sc_btn").on("click", applyQuery);
    $("#st").on("change", applyQuery);

    // 追納
    $(".ap-badge").on("click", notifyAdditionalPeriod);

    // 放棄ダイアログ上の制御
    $("#btn-abandon-yes").on("click", e => {
        // idを取得
        let id = $("#dlg-abandon-id").val();
        // 更新をリクエスト
        $.ajax({
            url: '/props/api/delete',
            type: 'POST',
            dataType: 'json',
            data: { id: id, _csrf: csrfToken }
        })
            .done(data => {
                // 結果の確認
                if (!data.result) {
                    $("#dlg-abandon-msg").text(data.message);
                    return;
                }
                // 一覧から権利を消す
                removePropFromTable(data.id);
                $("#dlg-abandon").modal("hide");
            })
            .fail((jqXHR, textStatus, errorThrown) => {
                if (jqXHR.status == 401) {
                    window.location.href = "/login";
                    return;
                }
                console.log(textStatus);
            });
    });
    $("#btn-abandon-no").on("click", e => {
        // ダイアログを閉じる
        $("#dlg-abandon").modal("hide");
    });

    // 検索条件のクリアー
    $("#sc_qry_c").on("click", e => {
        $("#sc_qry").val("");
    });

    initData.forEach((data) => {
        showPropInfo(data.Id, data);
    });

    // カートの件数をチェック
    checkCart();

    if (specId !== undefined) {
        $(`.editBtn[value='${specId}']`)[0].click();
    }
});
