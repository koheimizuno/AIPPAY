/**
 * 受領書・納付書のアップロードダイアログを開く
 */
function openUploadDialog() {

    $("#ulDlgMsg").empty();
    $("#ulDlg").modal("show");

}

/**
 * アップロードダイアログ上のアップロード済みリストを更新する
 */
function refreshUploadedList() {

    let reqId = $("#uld-key-req").val();
    let propId = $("#uld-key-prop").val();

    // アップロード済みファイル情報の取得
    $.ajax({
        url: '/s/reqs/api/uploaded',
        type: 'POST',
        dataType: 'json',
        data: { Request: reqId, Property: propId }
    })
    .done((data) => {

        // リストの表示
        let ul = $("#uld-filelist");
        ul.empty();

        if (data.UploadedFiles) {
            for (let file of data.UploadedFiles) {
                let href = `/s/reqs/api/download/${reqId}/${propId}/${file.Index}`;
                let text = file.Name;
                let subTexts = [];
                if (file.IsProcedurePaper) {
                    subTexts.push("{{ UI.Pages.Request.TEXT000009 }}");
                }
                if (file.IsReceiptPaper) {
                    subTexts.push("{{ UI.Pages.Request.TEXT000010 }}");
                }
                subTexts.push(file.UploadedTime);
                if (subTexts.length > 0) {
                    text += " [" + subTexts.join(", ") + "]";
                }
                ul.append($(`<li><a href="${href}">${text}</a></li>`));
            }
        }

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        showMessage(textStatus);
    });

}

/**
 * 領収書発送書類の作成ダイアログを開く
 */
function openReceiptDialog(reqId, propId) {

    $("#dlg-receipt-req-id").val(reqId);
    $("#dlg-receipt-prop-id").val(propId);

    // 依頼に関連付けられたユーザー情報の取得
    $.ajax({
        url: '/s/reqs/api/receipt/user',
        type: 'POST',
        dataType: 'json',
        data: { Request: reqId, Property: propId }
    })
    .done((data) => {

        // 名前の表示（組織名を含む）
        let s = "";
        s += data.Organization ?? "";
        if (s) s += " ";
        s += s.Name ?? "";
        $("#dlg-receipt-name").text(s);

        // 住所の表示
        $("#dlg-receipt-addr").val(data.Address ?? "");

        // モーダルを表示する
        $("#dlg-receipt").modal("show");

    })
    .fail((ex) => {
        showMessage("ERROR");
    })

}

/**
 * 領収書発送書類の作成（ダイアログ上のボタンのイベントハンドラー）
 */
function makeSendingReceiptPaper(e) {

    // IDの取得
    let reqId = $("#dlg-receipt-req-id").val();
    let propId = $("#dlg-receipt-prop-id").val();

    // 住所の取得
    let addr = $("#dlg-receipt-addr").val();

    if (!addr || addr === "") {
        showMessage("{{ UI.Pages.Request.TEXT000158 }}");
        return;
    }

    // 依頼に関連付けられたユーザー情報の取得
    $.ajax({
        url: '/s/reqs/api/receipt/make',
        type: 'POST',
        dataType: 'json',
        data: { Request: reqId, Property: propId, Address: addr }
    })
    .done((data) => {

        // 結果の確認
        if (!data.Result) {
            showMessage(data.Message);
        }

        // 表示の更新
        refreshRowOnTable(reqId);

        // ダウンロードの開始
        window.location.href = data.Url;

    })
    .fail((ex) => {
        showMessage("ERROR");
    })
    
}

/**
 * 権利の詳細を開く
 */
function showPropertyDetail(e) {

    let btn = $(e.currentTarget);
    let keys = btn.val().split("-");

    $.ajax({
        url: '/s/reqs/api/has',
        type: 'POST',
        dataType: 'json',
        data: {
            Request: keys[0],
            Property: keys[1]
        }
    })
    .done(data => {

        // ダイアログ
        let dlg = $("#dtl-modal-1");

        // 依頼番号
        dlg.find(".modal-title").text(`#${data.RequestNumber} - ${data.lawName}${data.RegistrationNumber} - ${data.Country}`);

        // リスト
        let ul1 = $("#dtl-modal-1 .dtl1-prop-1");
        let li;
        ul1.empty();

        // ユーザー
        if (data.userOrganization) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000091 }}", data.userOrganization);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000092 }}", data.userName);
        li.addClass("ji-label-content-item");
        ul1.append(li);

        // メールアドレス
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000093 }}", data.userEmail);
        li.addClass("ji-label-content-item");
        ul1.append(li);

        // 受任名義
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000065 }}", data.AgentName);
        li.addClass("ji-label-content-item");
        ul1.append(li);
                
        ul1 = $("#dtl-modal-1 .dtl1-prop-2");
        ul1.empty();

        // 国・地域
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000016 }}", data.Country);
        li.addClass("ji-label-content-item");
        ul1.append(li);

        // 法域
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000017 }}", data.lawName);
        li.addClass("ji-label-content-item");
        ul1.append(li);

        // 登録番号
        li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000018 }}", data.RegistrationNumber);
        li.addClass("ji-label-content-item");
        ul1.append(li);

        // 名称
        if (data.Subject) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000019 }}", data.Subject);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 権利者
        if (data.Holders) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000020 }}", data.Holders);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 出願日
        if (data.ApplicationDate_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000174 }}", data.ApplicationDate_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 審査請求日
        if (data.ExamClaimedDate_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000175 }}", data.ExamClaimedDate_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 登録日
        if (data.RegistrationDate_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000176 }}", data.RegistrationDate_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 請求項数
        if (data.NumberOfClaims) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000071 }}", data.NumberOfClaims);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 区分
        if (data.OriginalClasses) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000171 }}", data.OriginalClasses.join(","));
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 納付済年分
        if (data.PaidYears) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000173 }}", data.PaidYears);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        ul1 = $("#dtl-modal-1 .dtl1-prop-3");
        ul1.empty();

        // 更新する区分
        if (data.Classes) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000172 }}", data.Classes.join(","));
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 納付する年分
        if (data.law == 'Trademark') {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000073 }}", data.Years);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        } else {
            if (data.YearTo) {
                if (data.YearFrom && data.YearTo != data.YearFrom) {
                    li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000073 }}", `${data.YearFrom}-${data.YearTo}`);
                    li.addClass("ji-label-content-item");
                    ul1.append(li);
                } else {
                    li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000073 }}", data.YearTo);
                    li.addClass("ji-label-content-item");
                    ul1.append(li);
                }
            }
        }

        // 手続期限
        if (data.NextProcedureLimit_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000070 }}", data.NextProcedureLimit_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 依頼日時
        if (data.RequestedTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000004 }}", data.RequestedTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 入金日
        if (data.PaidTime_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000006 }}", data.PaidTime_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        } else if (data.PayLimit_Date) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000198 }}", data.PayLimit_Date);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 書類作成日
        if (data.PaperMadeTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000186 }}", data.PaperMadeTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 手続完了日
        if (data.CompletedTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000187 }}", data.CompletedTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 完了報告書送信日時
        if (data.CompletedReportSentTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000188 }}", data.CompletedReportSentTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // 領収書送付状作成日時
        if (data.SendingReceiptTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000189 }}", data.SendingReceiptTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // キャンセル日時
        if (data.CanceledTime_DateTime) {
            li = createLabelContentItem("li", "div", "{{ UI.Pages.Request.TEXT000190 }}", data.CanceledTime_DateTime);
            li.addClass("ji-label-content-item");
            ul1.append(li);
        }

        // ダウンロード用のURL
        dlg.find(".dtl-dl-invoice").attr("href", data.Urls.Invoice ?? "");
        dlg.find(".dtl-dl-del").attr("href", data.Urls.Deletion ?? "");
        dlg.find(".dtl-dl-hoju").attr("href", data.Urls.Hoju ?? "");
        dlg.find(".dtl-dl-jpo").attr("href", data.Urls.JpoPayment ?? "");
        dlg.find(".dtl-dl-gembo").attr("href", data.Urls.Gembo ?? "");

        // 手続リスト
        let ul = dlg.find(".dtl-procs");
        ul.empty();
        if (data.Procedures) {
            for (let item of data.Procedures) {
                let li = $("<li></li>");
                li.text(item);
                ul.append(li);
            }
        }

        // 庁費用
        let tbl = dlg.find(".dtl1-price-office > tbody");
        let row = tbl.find("tr");
        for (let j = 1; j < row.length; j++) {
            row.eq(j).remove();
        }
        row = row.eq(0);
        if (!data.Fees || !data.Fees.Office) {
            row.addClass("d-none");
        } else {
            for (let i = 0; i < data.Fees.Office.length; i++) {
                if (i > 0) {
                    row = row.eq(0).clone();
                    tbl.append(row);
                } else {
                    row.removeClass("d-none");
                }
                let cells = row.find("td");
                cells.eq(0).text(data.Fees.Office[i].Subject ?? "");
                cells.eq(1).find(".price").text(data.Fees.Office[i].Price ?? "");
                cells.eq(1).find(".currency-unit").text(data.Fees.Office[i].Currency ?? "");
                cells.eq(2).find(".price").text(data.Fees.Office[i].ExchangedPrice ?? "");
                cells.eq(2).find(".currency-unit").text(data.Fees.Office[i].ExchangedCurrency ?? "");
            }
        }

        // 事務所手数料
        tbl = dlg.find(".dtl1-price-agent > tbody");
        row = tbl.find("tr");
        for (let j = 1; j < row.length; j++) {
            row.eq(j).remove();
        }
        row = row.eq(0);
        if (!data.Fees || !data.Fees.Agent) {
            row.addClass("d-none");
        } else {
            for (let i = 0; i < data.Fees.Agent.length; i++) {
                if (i > 0) {
                    row = row.eq(0).clone();
                    tbl.append(row);
                } else {
                    row.removeClass("d-none");
                }
                let cells = row.find("td");
                cells.eq(0).text(data.Fees.Agent[i].Subject ?? "");
                cells.eq(1).find(".price").text(data.Fees.Agent[i].Price ?? "");
                cells.eq(1).find(".currency-unit").text(data.Fees.Agent[i].Currency ?? "");
                cells.eq(2).find(".price").text(data.Fees.Agent[i].ExchangedPrice ?? "");
                cells.eq(2).find(".currency-unit").text(data.Fees.Agent[i].ExchangedCurrency ?? "");
            }
        }

        // 合計請求金額
        if (data.total) {
            dlg.find(".dtl1-total .price").text(data.total.price ?? "");
            dlg.find(".dtl1-total .currency-unit").text(data.total.currency ?? "");
        } else {
            dlg.find(".dtl1-total .price").text("");
            dlg.find(".dtl1-total .currency-unit").text("");
        }

        // その他の権利
        dlg.find(".dtl1-others").empty();
        if (data.others && data.others.length > 0) {
            for (let o of data.others) {
                let li = $("<li></li>").text(`${o.country} - ${o.law} - ${o.registrationNumber}`);
                dlg.find(".dtl1-others").append(li);
            }
            dlg.find(".dtl1-others-area").removeClass("d-none");
        } else {
            dlg.find(".dtl1-others-area").addClass("d-none");
        }

        // アップロードされたファイル
        dlg.find(".dtl1-files").empty();
        if (data.files && data.files.length > 0) {
            for (let f of data.files) {
                let a = $("<a></a>").text(f.name).attr("href", f.url);
                let li = $("<li></li>").append(a);
                dlg.find(".dtl1-files").append(li);
            }
            dlg.find(".dtl1-files-area").removeClass("d-none");
        } else {
            dlg.find(".dtl1-files-area").addClass("d-none");
        }

        // キャンセル
        if (data.CanceledTime_DateTime) {
            dlg.find("#dtl-btn-cancel").val("");
            dlg.find("#dtl-btn-cancel").prop("disabled", true);
            dlg.find("#dtl-btn-cancel").addClass("d-none");
            dlg.find("#dtl-cancel-area > p").text(`{{ UI.Pages.Request.TEXT000051 }} (${data.CanceledTime_DateTime})`);
        } else {
            dlg.find("#dtl-btn-cancel").val(keys.join("-"));
            dlg.find("#dtl-btn-cancel").prop("disabled", false);
            dlg.find("#dtl-btn-cancel").removeClass("d-none");
            dlg.find("#dtl-cancel-area > p").text("");
        }

        // モーダル領域の表示
        $("#dtl-modal-1").modal("show");

    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        showMessage(textStatus);
    })
    .always(() => {
        btn.prop("disabled", false);
        $(e.currentTarget).removeClass("active");
    });
}

/**
 * テーブル上の行の内容を更新する
 */
function refreshAllRowsOnTable() {

    let rows = $(".ji-table-reqs tbody tr");

    for (let i = 0; i < rows.length; i++) {

        // 行を取得
        let row = rows.eq(i);

        // IDを取得
        let id = row.attr('id').split("-")[1];

        // 更新
        refreshRowOnTable(id);

    }

}

/**
 * テーブル上の行の内容を更新する
 */
function refreshRowOnTable(reqId) {

    $.ajax({
        url: '/s/reqs/api/req/for/list', type: 'POST', dataType: 'json',
        data: { Key: reqId }
    })
    .done((data) => {
        showOnList(data);
    });

}

/**
 * 依頼のステータスを入金確認済にする
 */
function paidAndMakePaper(reqId, propId) {

    // POST送信
    $.ajax({
        url: '/s/reqs/api/paid',
        type: 'POST',
        dataType: 'json',
        data: {requestId: reqId, propertyId: propId}
    })
    .done((data) => {
        refreshRowOnTable(reqId);
        let area = $("#download-dummy");
        area.empty();
        if (data.url) {
            let a = $(`<a href="${data.url}" download>1</a>`);
            area.append(a);
        }
        if (data.url2) {
            let a = $(`<a href="${data.url2}" download>2</a>`);
            area.append(a);
        }
        if (data.url3) {
            let a = $(`<a href="${data.url3}" download>3</a>`);
            area.append(a);
        }
        let links = document.querySelectorAll("#download-dummy > a");
        links.forEach((elem) => { elem.click(); });
    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        showMessage(textStatus);
    });

}

/**
 * 依頼のステータスを見積提示済にする
 */
function updateEstimated(reqId) {

    $(".ji-form-id-req").val(reqId);
    $("#ji-form-est").submit();

}

/**
 * 依頼/権利のステータスを対応完了にする
 */
function updateCompleted(reqId, propId) {

    $(".ji-form-id-req").val(reqId);
    $(".ji-form-id-prop").val(propId);
    $("#ji-form-comp").submit();

}

/**
 * 依頼/権利をキャンセル扱いにする
 */
function updateCanceled(e) {

    let btn = $("#dtl-btn-cancel");
    let keys = btn.val().split("-");

    let pwdBox = $("#dlg-cancel-pwd");
    let pwd = pwdBox.val();

    if (!pwd || pwd != "jipps123") {
        $("#dlg-cancel-msg").text("{{ UI.Pages.Request.TEXT000254 }}");
        return;
    }

    $(".ji-form-id-req").val(keys[0]);
    $(".ji-form-id-prop").val(keys[1]);
    $("#ji-form-cancel").submit();

}

/**
 * 関連ファイルのアップロードを実行する
 */
function doUpload(formData) {

    // ファイルが1つも無ければ実行しない。
    if (!formData.has("file_0")) return;

    // 実行ボタンの取得 + 無効化
    let btn = $("#doUlBtn");
    btn.prop("disabled", true);

    // ローディングを表示
    showLoadingOverlay();

    // POST送信
    $.ajax({
        url: '/s/reqs/api/upload',
        type: 'POST',
        dataType: 'json',
        cache: false,
        contentType: false,
        processData: false,
        data: formData
    })
    .done((data) => {
        $("#ulDlgMsg").empty();
        if (data.messages) {
            for (let msg of data.messages) {
                $("#ulDlgMsg").append($("<li></li>").text(msg));
            }
        }
        if (data.updatedIds) {
            for (let id of data.updatedIds) {
                refreshRowOnTable(id);
            }
        }
    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        showMessage(textStatus);
    })
    .always(() => {
        hideLoadingOverlay();
        btn.prop("disabled", false);
        $("#drp1").removeClass("active");
    });

}

/**
 * 一覧上の依頼情報を更新する。
 */
function showOnList(req) {

    // 依頼情報の行を取得
    let row = $("tr.row-" + req._id);

    // ユーザー名
    if (req.UserOrganization) {
        let elem = row.find(".rv-user-org");
        elem.removeClass("d-none");
        elem.text(req.UserOrganization);
    } else {
        let elem = row.find(".rv-user-org");
        elem.addClass("d-none");
        elem.text("");
    }
    row.find(".rv-user-name").text(req.UserName ?? "");
    row.find(".rv-user-email").text(req.UserEmail ?? "");
    // 依頼日
    if (req.RequestedTime_DateTime) {
        let p = req.RequestedTime_DateTime.split(" ");
        row.find(".rv-req-time > p.date").text(p[0]);
        row.find(".rv-req-time > p.time").text(p[1]);
    } else {
        row.find(".rv-req-time > p").text("");
    }
    // 請求金額
    if (req.TotalAmount) {
        row.find(".rv-total-amount > .price").text(req.TotalAmountText);
        row.find(".rv-total-amount > .currency-unit").text(req.Currency);
    } else {
        row.find(".rv-total-amount > .price").text("");
        row.find(".rv-total-amount > .currency-unit").text("");
    }

    // 権利情報の表示
    for (let i = 0; i < req.Properties.length; i++) {

        let prop = req.Properties[i];

        row = $(`tr#row-${req._id}-${i}`);

        // 国, 法域, 登録番号
        row.find(".rv-country").text(prop.CountryDescription ?? "");
        row.find(".rv-law").text(prop.LawName ?? "");
        row.find(".rv-reg-num").text(prop.RegistrationNumber ?? "");

        // 整理番号
        row.find(".rv-man-num").text(prop.ManagementNumber ?? "-");
        row.find(".rv-man-num").attr("data-row-key", `${req._id}-${prop.Property}`);

        // 権利者
        row.find(".rv-holders").text(prop.Holders_F);

        // 次回納付期限
        row.find(".rv-next-limit").text(prop.NextProcedureLimit_Date ?? "");

        // 次回納付期限
        row.find(".rv-exp-date").text(prop.ExpirationDate_Date ?? "");

        // 事務所手数料
        if (prop.AgentFee) {
            row.find(".rv-agent-fee .price").text(prop.AgentFee.Amount_F);
            row.find(".rv-agent-fee .currency-unit").text(prop.AgentFee.Currency ?? "");
        }

        // 特許庁手数料
        if (prop.OfficialFee) {
            row.find(".rv-office-fee .price").text(prop.OfficialFee.Amount_F);
            row.find(".rv-office-fee .currency-unit").text(prop.OfficialFee.Currency ?? "");
        }

        // 備考
        row.find(".rv-memo-box").val(prop.Memo ?? "");
        row.find(".rv-memo-up").prop("disabled", true);

        // 日本以外は納付書・受領書未対応
        if (prop.Country != 'JP') {
            row.find(".dlBtn").addClass("d-none");
        }

        // ボタンに値を設定
        row.find(".rv-btn-prop").val(`${req._id}-${prop.Property}`);

        // キャンセル確認
        if (prop.CanceledTime) {

            row.addClass("canceled-prop");
            row.find(".btn-paid-and-paper").addClass("button-deprecated");
            row.find(".btn-paid-and-paper").prop("disabled", true);
            row.find(".rcpBtn").addClass("button-deprecated");
            row.find(".rcpBtn").prop("disabled", true);
            row.find(".rcpBtn").addClass("button-deprecated");
            row.find(".rcpBtn").prop("disabled", true);
            row.find(".rv-up-time").text("{{ UI.Vocabulary.Canceled }}");

        } else {

            row.removeClass("canceled-prop");
            row.find(".btn-paid-and-paper").prop("disabled", false);
            row.find(".rcpBtn").prop("disabled", false);
            row.find(".rcpBtn").prop("disabled", false);

            // 納付書
            if (prop.PaidTime || prop.PaperMadeTime) {
                row.find(".btn-paid-and-paper").addClass("button-deprecated");
                row.find(".rv-paper-time").text(prop.PaidTime_Date ?? prop.PaperMadeTime_Date ?? "");
            } else {
                row.find(".btn-paid-and-paper").removeClass("button-deprecated");
                row.find(".rv-paper-time").empty();
            }

            // 手続完了日
            if (prop.CompletedTime) {
                row.find(".rv-up-time").text(prop.CompletedTime_Date);
            } else {
                row.find(".rv-up-time").empty();
            }

            // 領収書送付状ボタン
            if (prop.SendingReceiptTime) {
                row.find(".rcpBtn").addClass("button-deprecated");
                row.find(".rv-rep-time").text(prop.SendingReceiptTime_Date);
            } else {
                row.find(".rcpBtn").removeClass("button-deprecated");
                row.find(".rv-rep-time").empty();
            }

        }

    }

}

/**
 * キャンセルの確認ダイアログを表示する
 */
function confirmCancel(e) {

    $("#dtl-modal-1").modal("hide");
    $("#dlg-cancel-pwd").val("");
    $("#dlg-cancel-msg").text("");
    $("#dlg-cancel").modal("show");

}

/**
 * キャンセルの実行
 */
function cancelRequest(e) {

    let keys = $("#dtl-btn-cancel").val().split("-");
    updateCanceled(keys[0], keys[1]);

}

/**
 * 備考の更新
 */
function updateMemo(e) {
    let btn = $(e.currentTarget);
    let cell = btn.parents('.cell-memo').eq(0);
    let box = cell.find('.rv-memo-box');
    let memo = box.val() ?? "";
    let keys = btn.val().split("-");
    $.ajax({
        url: '/s/reqs/api/memo',
        type: 'POST',
        dataType: 'json',
        data: {
            reqId: keys[0],
            propId: keys[1],
            memo: memo
        }
    })
    .done((data) => {
        if (data.result) {
            refreshRowOnTable(keys[0]);
        }
    })
    .fail((jqXHR, textStatus, errorThrown) => {
        if (jqXHR.status == 401) {
            window.location.href = "/login";
            return;
        }
        showMessage(textStatus);
    });
}

function openManNumberDialog(e) {
    
    var cell = $(e.currentTarget);
    var key = cell.attr("data-row-key");
    var keys = key.split("-");

    $.ajax({
        url: '/s/reqs/api/mannum/get',
        type: 'POST',
        dataType: 'json',
        data: {
            id: keys[1]
        }
    })
    .done((data) => {
        if (data.result) {
            $("#dlg-mannum-text").val(data.managementNumber ?? "");
            $("#dlg-mannum-req-id").val(keys[0]);
            $("#dlg-mannum-prop-id").val(keys[1]);
            $("#dlg-mannum").modal("show");
        }
    })
    .fail((ex) => {
        console.log(ex);
    });

}

function updateManagementNumber(e) {

    var reqId = $("#dlg-mannum-req-id").val();
    var propId = $("#dlg-mannum-prop-id").val();
    var manNum = $("#dlg-mannum-text").val() ?? "";

    $.ajax({
        url: '/s/reqs/api/mannum/update',
        type: 'POST',
        dataType: 'json',
        data: {
            id: propId,
            managementNumber: manNum
        }
    })
    .done((data) => {
        if (data.result) {
            $("#dlg-mannum").modal("hide");
            refreshRowOnTable(reqId);
        }
    })
    .fail((ex) => {
        console.log(ex);
    });

}

/**
 *
 */
$(window).on("load", e => {

    // 見積提示ボタン
    $(".estBtn").on("click", e => {
        let elem = $(e.currentTarget);
        let id = elem.val();
        updateEstimated(id);
    });

    // 入金確認ボタン
    $(".btn-paid-and-paper").on("click", e => {
        let elem = $(e.currentTarget);
        let ids = elem.val().split("-");
        paidAndMakePaper(ids[0], ids[1]);
    });

    // 対応完了ボタン
    $(".dnBtn").on("click", e => {
        let elem = $(e.currentTarget);
        let ids = elem.val().split("-");
        updateCompleted(ids[0], ids[1]);
    });

    // 提出書類ボタン（提出書類のアップロード）
    $("#btn-upload-open").on("click", e => {
        openUploadDialog();
    });

    // アップロードボタン（実行）
    $("#doUlBtn").on("click", e => {
        let p = new FormData($("#ulDlgFm")[0]);
        if (!p.has("file_0")) return;
        doUpload(p);
    });
    $("#drp1").on("dragover", e => {
        oe = e.originalEvent;
        oe.stopPropagation();
        oe.preventDefault();
        oe.dataTransfer.dropEffect = "copy";
        $(e.currentTarget).addClass("active");
    });
    $("#drp1").on("dragleave", e => {
        oe = e.originalEvent;
        oe.stopPropagation();
        oe.preventDefault();
        $(e.currentTarget).removeClass("active");
    });
    $("#drp1").on("drop", e => {
        $("#ulDlgMsg").empty();
        oe = e.originalEvent;
        oe.stopPropagation();
        oe.preventDefault();
        let files = oe.dataTransfer.files;
        let p = new FormData($("#ulDlgFm")[0]);
        let cnt = 0;
        p.delete("file_0");
        for (let i = 0; i < files.length; i++) {
            let file = files[i];
            //if (file.type == "application/pdf") {
                p.append("file_" + cnt, file);
                cnt++;
            //}
        }
        if (cnt < 1) {
            $("#ulDlgMsg").empty();
            $("#ulDlgMsg").append($("<li></li>").text("{{ UI.Error.InvalidFileFormat }}"));
            $(e.currentTarget).removeClass("active");
        }
        doUpload(p);
    });

    // 領収書発送ボタン
    $(".rcpBtn").on("click", (e) => {
        let elem = $(e.currentTarget);
        let keys = elem.val().split("-");
        openReceiptDialog(keys[0], keys[1]);
    });

    // 領収書発送書類作成の実行ボタン
    $("#dlg-receipt-make").on("click", makeSendingReceiptPaper);

    // 権利の詳細を開く
    $(".dldBtn").on("click", showPropertyDetail);

    // キャンセル関係
    $("#dtl-btn-cancel").on("click", confirmCancel);
    $("#dlg-cancel-yes").on("click", updateCanceled);
    $("#dlg-cancel-no").on("click", (e) => { $("#dlg-cancel").modal("hide"); });

    // メモの更新
    $(".rv-memo-up").on("click", updateMemo);
    $(".rv-memo-box").on("change", (e) => {
        let box = $(e.currentTarget);
        let btn = box.parents(".cell-memo").find(".rv-memo-up");
        btn.prop("disabled", false);
    });
    $(".rv-memo-box").on("keydown", (e) => {
        let box = $(e.currentTarget);
        let btn = box.parents(".cell-memo").find(".rv-memo-up");
        btn.prop("disabled", false);
    });

    // 整理番号
    $(".rv-man-num").on("click", openManNumberDialog);
    $("#dlg-mannum-update").on("click", updateManagementNumber);

    // 明細を表示
    for (let data of initData) {
        showOnList(data);
    }

});
