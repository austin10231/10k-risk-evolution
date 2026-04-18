(function () {
  function getLangFromUrl() {
    var params = new URLSearchParams(window.location.search);
    var lang = params.get("lang");
    return lang === "zh" ? "zh" : "en";
  }

  function getStoredLang() {
    try {
      var stored = window.localStorage.getItem("risklens_lang");
      return stored === "zh" ? "zh" : "en";
    } catch (e) {
      return "en";
    }
  }

  function setStoredLang(lang) {
    try {
      window.localStorage.setItem("risklens_lang", lang);
    } catch (e) {}
  }

  function getEffectiveLang() {
    var fromUrl = getLangFromUrl();
    if (new URLSearchParams(window.location.search).has("lang")) {
      return fromUrl;
    }
    return getStoredLang();
  }

  function withLangParam(href, lang) {
    if (!href) return href;
    if (
      href.startsWith("#") ||
      href.startsWith("mailto:") ||
      href.startsWith("tel:") ||
      href.startsWith("javascript:")
    ) {
      return href;
    }
    if (/^https?:\/\//i.test(href)) {
      return href;
    }
    var url = new URL(href, window.location.href);
    url.searchParams.set("lang", lang);
    return url.pathname + url.search + url.hash;
  }

  function appendLangToInternalLinks(lang) {
    document.querySelectorAll("a[href]").forEach(function (a) {
      if (a.dataset.langIgnore === "true") return;
      var href = a.getAttribute("href");
      var updated = withLangParam(href, lang);
      if (updated) a.setAttribute("href", updated);
    });
  }

  function applyTextMap(textMap) {
    if (!textMap) return;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent) continue;
      var tag = parent.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") continue;
      var raw = node.nodeValue;
      var trimmed = raw.trim();
      if (!trimmed) continue;
      var replacement = textMap[trimmed];
      if (replacement) {
        node.nodeValue = raw.replace(trimmed, replacement);
      }
    }

    document.querySelectorAll("[placeholder]").forEach(function (el) {
      var value = el.getAttribute("placeholder");
      if (textMap[value]) el.setAttribute("placeholder", textMap[value]);
    });
    document.querySelectorAll("[title]").forEach(function (el) {
      var title = el.getAttribute("title");
      if (textMap[title]) el.setAttribute("title", textMap[title]);
    });
    document.querySelectorAll("[aria-label]").forEach(function (el) {
      var label = el.getAttribute("aria-label");
      if (textMap[label]) el.setAttribute("aria-label", textMap[label]);
    });
  }

  function syncLangQuery(lang) {
    var params = new URLSearchParams(window.location.search);
    params.set("lang", lang);
    var next = window.location.pathname + "?" + params.toString() + window.location.hash;
    window.history.replaceState({}, "", next);
  }

  function mountSwitcher(options) {
    var config = options || {};
    var textMap = config.textMap || null;
    var titleMap = config.titleMap || null;
    var menuId = config.menuId || "lang-menu";
    var btnId = config.buttonId || "lang-btn";
    var labelId = config.labelId || "lang-label";

    var lang = getEffectiveLang();
    setStoredLang(lang);
    syncLangQuery(lang);
    appendLangToInternalLinks(lang);

    if (lang === "zh") {
      applyTextMap(textMap);
      if (titleMap && titleMap.zh) document.title = titleMap.zh;
      document.documentElement.setAttribute("lang", "zh-CN");
    } else {
      if (titleMap && titleMap.en) document.title = titleMap.en;
      document.documentElement.setAttribute("lang", "en");
    }

    var menu = document.getElementById(menuId);
    var btn = document.getElementById(btnId);
    var label = document.getElementById(labelId);
    if (!menu || !btn || !label) return;

    label.textContent = lang === "zh" ? "中文" : "EN";

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      menu.classList.toggle("hidden");
    });

    document.addEventListener("click", function () {
      menu.classList.add("hidden");
    });

    menu.querySelectorAll("[data-lang]").forEach(function (item) {
      item.addEventListener("click", function (e) {
        e.preventDefault();
        var nextLang = item.getAttribute("data-lang") === "zh" ? "zh" : "en";
        setStoredLang(nextLang);
        var params = new URLSearchParams(window.location.search);
        params.set("lang", nextLang);
        window.location.search = params.toString();
      });
    });
  }

  window.RiskLensLang = {
    mountSwitcher: mountSwitcher,
  };
})();
