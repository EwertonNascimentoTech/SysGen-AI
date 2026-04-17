/**
 * Executado em páginas do export Stitch abertas via blob: — intercepta links relativos
 * e carrega o destino pela API com Bearer (localStorage), para o layout voltar a funcionar.
 */
(function () {
  "use strict";
  var TOKEN_KEY = "pgia_token";
  var pid = window.__STITCH_P__;
  var currentRel = window.__STITCH_R__;
  var viewerScriptSrc = window.__STITCH_SCRIPT_SRC__;
  try {
    delete window.__STITCH_P__;
    delete window.__STITCH_R__;
    delete window.__STITCH_SCRIPT_SRC__;
  } catch (e) {}

  if (typeof pid !== "number" || typeof currentRel !== "string") return;

  function authHeaders() {
    var h = new Headers();
    var t = localStorage.getItem(TOKEN_KEY);
    if (t) h.set("Authorization", "Bearer " + t);
    return h;
  }

  function resolveViewerSrc() {
    if (viewerScriptSrc) return viewerScriptSrc;
    var list = document.getElementsByTagName("script");
    for (var i = list.length - 1; i >= 0; i--) {
      var s = list[i].src || "";
      if (s.indexOf("stitch-export-viewer.js") !== -1) return s.split("?")[0];
    }
    return "/stitch-export-viewer.js";
  }

  var resolvedViewerSrc = resolveViewerSrc();

  function fetchExportBlob(rel) {
    return fetch(
      "/api/projects/" + pid + "/prototipo/stitch-api/export-file?rel=" + encodeURIComponent(rel),
      { headers: authHeaders(), credentials: "same-origin" },
    ).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (txt) {
          throw new Error((txt && txt.slice(0, 400)) || r.statusText);
        });
      }
      return r.blob();
    });
  }

  function bootstrapHtml(text, nextRel) {
    var cfg =
      "<script>window.__STITCH_P__=" +
      JSON.stringify(pid) +
      ";window.__STITCH_R__=" +
      JSON.stringify(nextRel) +
      ";window.__STITCH_SCRIPT_SRC__=" +
      JSON.stringify(resolvedViewerSrc) +
      ";<\/script><script src=\"" +
      resolvedViewerSrc.replace(/"/g, "&quot;") +
      "\" defer><\/script>";
    if (text.indexOf("</head>") !== -1) {
      return text.replace("</head>", cfg + "</head>");
    }
    return cfg + text;
  }

  function resolveExportHref(href, cur) {
    var h = (href || "").trim();
    if (!h || /^javascript:/i.test(h)) return null;
    if (h === "#" || (h.charAt(0) === "#" && h.indexOf("/") === -1)) return { hash: true };
    if (/^[a-z][a-z0-9+.-]*:/i.test(h)) {
      if (/^https?:\/\//i.test(h) || h.indexOf("//") === 0) return { external: true };
      return { external: true };
    }
    try {
      var base = "http://_stitch_export_/" + cur.replace(/^\/+/, "");
      var u = new URL(h, base);
      var p = u.pathname.replace(/^\/+/, "");
      return { rel: p };
    } catch (e) {
      return null;
    }
  }

  function navigate(nextRel, newTab) {
    fetchExportBlob(nextRel).then(function (blob) {
      var type = blob.type || "";
      var isHtml = /html/i.test(type) || /\.html?$/i.test(nextRel);
      if (isHtml) {
        return blob.text().then(function (text) {
          var htmlOut = bootstrapHtml(text, nextRel);
          var url = URL.createObjectURL(new Blob([htmlOut], { type: "text/html;charset=utf-8" }));
          if (newTab) {
            var w = window.open(url, "_blank", "noopener,noreferrer");
            if (!w) {
              URL.revokeObjectURL(url);
              alert("Permita janelas emergentes para abrir o destino.");
            } else {
              setTimeout(function () {
                URL.revokeObjectURL(url);
              }, 120000);
            }
          } else {
            window.location.href = url;
            setTimeout(function () {
              URL.revokeObjectURL(url);
            }, 120000);
          }
        });
      }
      var url = URL.createObjectURL(blob);
      if (newTab) {
        window.open(url, "_blank");
        setTimeout(function () {
          URL.revokeObjectURL(url);
        }, 120000);
      } else {
        window.location.href = url;
        setTimeout(function () {
          URL.revokeObjectURL(url);
        }, 120000);
      }
    }).catch(function (e) {
      alert(e && e.message ? e.message : String(e));
    });
  }

  document.addEventListener(
    "click",
    function (ev) {
      var a = ev.target && ev.target.closest && ev.target.closest("a[href]");
      if (!a) return;
      var href = a.getAttribute("href");
      if (href == null) return;
      var resolved = resolveExportHref(href, currentRel);
      if (!resolved || resolved.external || resolved.hash) return;
      if (resolved.rel) {
        ev.preventDefault();
        ev.stopPropagation();
        navigate(resolved.rel, a.getAttribute("target") === "_blank");
      }
    },
    true,
  );
})();
