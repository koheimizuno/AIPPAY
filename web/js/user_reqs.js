/**
 * 一覧上に権利の情報を表示する
 */
function showOnList(data) {

    // 更新対象の行を取得する
    let tbl = $("#ji-table-reqs tbody");
    let row = tbl.find(`#row-${data.Id}-0`);

    // 表示
    row.find(".cell-req-date").html(markupDateText(data.RequestedTime_DateTime ?? ""));

    // ステータス
    row.find(".cell-status").text(data.StatusMessage ?? "");

    // 請求合計
    cell = row.find(".cell-amount-fee").empty();
    if (data.Currency && data.Currency in data.AmountsText) {
        cell.append($('<span class="price"></span>').text(data.AmountsText[data.Currency]));
        cell.append($('<span class="currency-unit"></span>').text(data.CurrencyLocal));
    }

    // 知的財産権
    for (let i in data.Properties) {

        // 行の特定
        row = tbl.find(`#row-${data.Id}-${i}`);

        let prop = data.Properties[i];

        // 登録番号等
        row.find(".cell-props")
            .empty()
            .append($('<span class="cell-country"></span>').text(prop.CountryDescription ?? ""))
            .append($('<span class="cell-law"></span>').text(prop.LawName ?? ""))
            .append($('<span class="cell-reg-num"></span>').text(prop.RegistrationNumber ?? ""));

        // 権利の名称
        row.find(".cell-subject").text(prop.Subject ?? "");

        // 庁費用
        let cell = row.find(".cell-official-fee").empty()
        if (prop.OfficialFeeText) {
            cell.append($('<span class="price"></span>').text(prop.OfficialFeeText));
            cell.append($('<span class="currency-unit"></span>').text(prop.OfficialFeeCurrencyLocal));
        }

        // 事務所費用
        cell = row.find(".cell-agent-fee").empty();
        if (prop.AgentFeeText) {
            cell.append($('<span class="price"></span>').text(prop.AgentFeeText));
            cell.append($('<span class="currency-unit"></span>').text(prop.AgentFeeCurrencyLocal));
        }

        // 小計（権利ごと）
        cell = row.find(".cell-total-fee").empty();
        if (prop.TotalFeeText) {
            cell.append($('<span class="price"></span>').text(prop.TotalFeeText));
            cell.append($('<span class="currency-unit"></span>').text(prop.TotalFeeCurrencyLocal));
        }
    
        // ステータス
        row.find(".cell-status").text(prop.StatusMessage);

    }

}

/**
 * 詳細ダイアログ上の情報を最新にする
 */
function showOnDialog(data, index) {

    // ダイアログ
    let dlg = $("#dlg1");
    let elem = null;

    // 依頼日時
    dlg.find(".dlg1-req-time").text(data.RequestedTime_DateTime);

    // 請求金額
    elem = $(".dlg1-amount");
    elem.empty();
    if (data.TotalAmountText) {
        elem.append($('<span class="price"></span>').text(data.TotalAmountText));
        elem.append($('<span class="currency-unit"></span>').text(data.CurrencyLocal));
    }

    // 権利の情報
    let prop = data.Properties[index];

    // 権利の情報
    let numTxt = [prop.CountryDescription ?? "", prop.LawName ?? "", prop.RegistrationNumber ?? ""].join(" ");
    $(".dlg1-req-num").text(numTxt);

    // 権利の名称
    $(".dlg1-subject").text(prop.Subject ?? "");

    // 手続の内容
    elem = $(".dlg1-procs");
    elem.empty();
    for (let proc of prop.Procedures) {
        elem.append($('<li></li>').text(proc));
    }

    // 料金内訳
    elem = $(".dlg1-price-area");
    elem.empty();

    // 特許庁印紙代
    if (prop.OfficialFeeText) {
        let content = $('<div class="content"></div>');
        content.append($('<span class="price"></span>').text(prop.OfficialFeeText));
        content.append($('<span class="currency-unit"></span>').text(prop.OfficialFeeCurrencyLocal));
        let box = $('<div class="ji-label-content-item"></div>');
        box.append($('<div class="label"></div>').text("{{ UI.Pages.Request.TEXT000023 }}"));
        box.append(content);
        let li = $('<li></li>').append(box);
        elem.append(li);
    }

    // 事務所料金
    if (prop.AgentFeeText) {
        let content = $('<div class="content"></div>');
        content.append($('<span class="price"></span>').text(prop.AgentFeeText));
        content.append($('<span class="currency-unit"></span>').text(prop.AgentFeeCurrencyLocal));
        let box = $('<div class="ji-label-content-item"></div>');
        box.append($('<div class="label"></div>').text("{{ UI.Pages.Request.TEXT000024 }}"));
        box.append(content);
        let li = $('<li></li>').append(box);
        elem.append(li);
    }

    // 小計
    if (prop.TotalFeeText) {
        let content = $('<div class="content"></div>');
        content.append($('<span class="price"></span>').text(prop.TotalFeeText));
        content.append($('<span class="currency-unit"></span>').text(prop.TotalFeeCurrencyLocal));
        let box = $('<div class="ji-label-content-item"></div>');
        box.append($('<div class="label"></div>').text("{{ UI.Pages.Request.TEXT000025 }}"));
        box.append(content);
        let li = $('<li></li>').append(box);
        elem.append(li);
    }

    // ステータス
    dlg.find(".dlg1-status").text(prop.StatusMessage ?? "");

    // 依頼に含まれる他の権利
    if (data.Properties.length > 1) {

        for (let i in data.Properties) {

            if (i == index) continue;

            // 情報のセット
            prop = data.Properties[i];
            let numTxt = [prop.CountryDescription ?? "", prop.LawName ?? "", prop.RegistrationNumber ?? ""].join(" ");
            $(".dlg1-others-area > ul").append($('<li></li>').text(numTxt));
    
        }

        $(".dlg1-others-area").removeClass("d-none");

    } else {

        $(".dlg1-others-area").addClass("d-none");

    }

    // ダウンロードリスト
    let dllist = dlg.find("#dlg1-dllist").empty();

    // 請求書のダウンロードリンク
    if (data.HasInvoice) {
        dllist.append($('<li></li>')
            .append($('<a></a>')
                .attr('href', '/reqs/api/invoice/' + data.Id)
                .text('{{ UI.Pages.Request.TEXT000053 }}'))
        );
    }

}

/**
 * 詳細ダイアログを開く
 */
function openDetailDialog(e) {

    // IDの取得
    btn = $(e.currentTarget);
    let ids = btn.val().split("-");
    let id = ids[0];
    let propIdx = ids[1]

    $("#dlg1 .dlg1-id").val(id);

    // APIに問い合わせ
    $.ajax({
        url: '/reqs/api/get',
        type: 'POST',
        dataType: 'json',
        data: { Id: id, Index: propIdx }
    })
    .done((data) => {

        // ダイアログ上に表示
        showOnDialog(data, propIdx);

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
 * 読み込み時
 */
$(window).on("load", (e) => {

    // イベントの登録
    $(".cell-btn-detail").on("click", openDetailDialog);

    // 情報をリストに表示する
    for (let data of initData) {
        showOnList(data);
    }

});