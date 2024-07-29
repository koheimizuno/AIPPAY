/**
 * カートに入っている権利の数を取得する
 */
function checkCart() {
    if ($("#cart-box").length == 0) return;
    $.ajax({
        url: '/props/api/cart', type: 'POST', dataType: 'json',
        data: {}
    })
    .done((data) => {
        if (data.count > 0) {
            $("#cart-box").removeClass("d-none");
            $("#cart-box-count").text(parseInt(data.count));
        } else {
            $("#cart-box").addClass("d-none");
        }
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
 * 依頼可否を更新する
 */
function checkRequestable(btn) {

    let id = btn.val();

    $.ajax({
        url: '/props/api/requestable', type: 'POST', dataType: 'json',
        data: { id: id }
    })
    .done((data) => {
        let span = btn.parents("td.cell-btn-cart").find(".msg-cart");
        if (data.requestable) {
            btn.removeClass("d-none");
            span.text("");
        } else {
            btn.addClass("d-none");
            span.text(data.message);
        }
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
 * 読み込み時
 */
$(window).on("load", (e) => {

    // 追加
    $("#btn-add").on("click", (e) => {
        $("#dlg-add-reg-num").val("");
        $("#dlg-add-addr").val("");
        $("#dlg-add-name").val("");
        $("#dlg-add-org").val("");
        $("#dlg-add").modal("show");
    });
    $("#dlg-add-add").on("click", (e) => {
        // モード判定
        let staffMode = false;
        if ($("#cart-box").length == 0) staffMode = true;
        $("#dlg-add-msg").text("");
        let country = "JP";
        let law = $("input[name='dlg-add-law']:checked").val();
        if (!law) {
            $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000125 }}");
            return;
        }
        let regNum = $("#dlg-add-reg-num").val();
        if (!regNum || regNum.trim() == "") {
            $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000126 }}");
            return;
        }
        if (country == "JP") {
            if (law == "Trademark") {
                if (!/^[0-9]{7,8}$/.test(regNum)) {
                    $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000127 }}");
                    return;
                }
            } else {
                if (!/^[0-9]{7}$/.test(regNum)) {
                    $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000127 }}");
                    return;
                }
            }
        }
        let manNum = $("#dlg-add-man-num").val();
        let addr = $("#dlg-add-addr").val();
        if (staffMode) {
            if (!addr || addr.trim() == "") {
                $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000128 }}");
                return;
            }
        }
        let userOrg = $("#dlg-add-org").val();
        let userName = $("#dlg-add-name").val();
        if (!userOrg && userOrg.trim() == "") userOrg = undefined;
        if (!userName && userName.trim() == "") userName = undefined;
        if (userOrg && !userName) {
            $("#dlg-add-msg").text("{{ UI.Pages.Property.TEXT000129 }}");
            return;
        } 
        let param = {
            country: country,
            law: law,
            registrationNumber: regNum
        };
        if (staffMode) {
            param.mailAddress = addr;
        } else {
            param.managementNumber = manNum;
        }
        if (userName) {
            param.userName = userName;
            if (userOrg) {
                param.userOrganization = userOrg;
            }
        }
        let apiUrl = staffMode ? '/s/kigen/api/reg' : '/kigen/api/reg';
        showLoadingOverlay();
        $.ajax({
            url: apiUrl,
            type: 'POST',
            dataType: 'json',
            data: param
        })
        .done((data) => {
            hideLoadingOverlay();
            if (data.result) {
                location.reload();
                return;
            } else {
                $("#dlg-add-msg").text(data.message);
            }
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            hideLoadingOverlay();
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            showMessage(textStatus);
        });

    });

    // 削除
    $(".btn-rm-prop").on("click", (e) => {
        let btn = $(e.currentTarget);
        let id = btn.val();
        $("#dlg-rm-id").val(id ?? "");
        $("#dlg-rm-msg").text("");
        $("#dlg-rm").modal("show");
    });
    $("#dlg-rm-btn-no").on("click", (e) => {
        $("#dlg-rm-id").val("");
        $("#dlg-rm").modal("hide");
    });
    $("#dlg-rm-btn-yes").on("click", (e) => {
        let pwdBox = $("#dlg2-rm-pwd");
        let pwd = pwdBox.val();
        if (!pwd || pwd != "jipps123") {
            $("#dlg-rm-msg").text("{{ UI.Pages.Property.TEXT000119 }}");
            return;
        }
        let propId = $("#dlg-rm-id").val();
        $.ajax({
            url: '/s/kigen/api/rm',
            type: 'POST',
            dataType: 'json',
            data: { propId: propId }
        })
        .done((data) => {
            if (data.result) {
                location.reload();
                return;
            }
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            showMessage(textStatus);
        });
    });

    // メモの更新
    $(".btn-up-memo").on("click", (e) => {
        let btn = $(e.currentTarget);
        let box = btn.parents(".cell-memo").find("textarea");
        let memo = box.val();
        let p = { propId: btn.val() };
        if (memo) {
            p.memo = memo;
        }
        $.ajax({
            url: '/s/kigen/api/memo',
            type: 'POST',
            dataType: 'json',
            data: p
        })
        .done((data) => {
            if (data.result) {
                btn.prop("disabled", true)
            }
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            showMessage(textStatus);
        });
    });
    $(".txt-memo").on("keydown", (e) => {
        let box = $(e.currentTarget).parents(".cell-memo").find(".btn-up-memo");
        box.prop("disabled", false);
    });
    $(".txt-memo").on("change", (e) => {
        let box = $(e.currentTarget).parents(".cell-memo").find(".btn-up-memo");
        box.prop("disabled", false);
    });

    // 整理番号の更新
    $(".btn-mannum").on("click", (e) => {
        let btn = $(e.currentTarget);
        let current = btn.text() ?? "";
        current = current.trim();
        if (current == "-") current = "";
        $("#dlg-mannum-man-num").val(current);
        $("#dlg-mannum-id").val(btn.val() ?? "");
        $("#dlg-mannum").modal("show");
    });
    $("#dlg-mannum-do").on("click", (e) => {
        let id = $("#dlg-mannum-id").val();
        let num = $("#dlg-mannum-man-num").val();
        num = (num ?? "").trim();
        let param = {id: id};
        if (num) param.managementNumber = num;
        $.ajax({
            url: '/kigen/api/mannum',
            type: 'POST',
            dataType: 'json',
            data: param
        })
        .done((data) => {
            if (data.result) {
                location.reload();
            }
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            showMessage(textStatus);
        });
    });

    // カートに追加
    $(".btn-cart").on("click", (e) => {

        let btn = $(e.currentTarget);
        let id = btn.val();
        $.ajax({
            url: '/props/api/req', type: 'POST', dataType: 'json',
            data: { id: id }
        })
        .done((data) => {
            if (!data.result) {
                if (data.invalidOwner) {
                    $("#dlg-chown-id").val(id);
                    $("#dlg-chown-msg-1").text(data.message);
                    $("#dlg-chown").modal("show");
                }
                return;
            }
            checkCart();
            checkRequestable(btn)
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
        });

    });

    // 担当者を変更してカートに追加
    $("#dlg-chown-btn-yes").on("click", (e) => {

        let id = $("#dlg-chown-id").val();

        $.ajax({
            url: '/props/api/reqf', type: 'POST', dataType: 'json',
            data: { id: id }
        })
        .done((data) => {
            if (!data.result) {
                $("#dlg-chown").modal("hide");
                return;
            }
            checkCart();
            let btn = $(`.btn-cart[value='${id}']`)
            checkRequestable(btn)
            $("#dlg-chown").modal("hide");
        })
        .fail((jqXHR, textStatus, errorThrown) => {
            if (jqXHR.status == 401) {
                window.location.href = "/login";
                return;
            }
            console.log(textStatus);
        });

    });
    $("#dlg-chown-btn-no").on("click", (e) => {
        $("#dlg-chown").modal("hide");
    });

    $(".btn-notfication").on("click", (e) => {
        let btn = $(e.currentTarget);
        let id = btn.val();
        $.ajax({
            url: '/kigen/api/silent',
            type: 'POST',
            dataType: 'json',
            data: { id: id }
        })
        .done((data) => {
            if (data.result) {
                let elem1 = btn.parents('.cell-notification');
                let elem2 = elem1.find('.msg-silent');
                if (data.silent) {
                    btn.addClass("btn-notfication-off");
                    btn.text("{{ UI.Pages.Property.TEXT000166 }}");
                    elem2.removeClass('d-none');
                    console.log(data);
                    elem2.find(".msg-silent-date").text(data.silentDate);
                } else {
                    btn.removeClass("btn-notfication-off");
                    btn.text("{{ UI.Pages.Property.TEXT000167 }}");
                    elem2.addClass('d-none');
                    elem2.find(".msg-silent-date").text("");
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
    });

    // カートのチェック
    checkCart();

    // 依頼可否の総チェック
    //let btns = $(".btn-cart");
    //for (let i = 0; i < btns.length; i++) {
    //    checkRequestable(btns.eq(i));
    //}

});