// ==UserScript==
// @name         Factorio Mod Downloader
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  Extension replacement for the Factorio Mod Downloader
// @author       kwimpcom
// @match        https://mods.factorio.com/*
// @icon         https://mods.factorio.com/favicon.ico
// @license      MIT
// @connect      127.0.0.1
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// ==/UserScript==

(function() {
    'use strict';

    console.log("Initialized.");

    /* ----------------------------- */
    /*           STYLES              */
    /* ----------------------------- */

    function injectStyles() {
        if (document.querySelector("#factorio-api-style")) return;

        const style = document.createElement('style');
        style.id = "factorio-api-style";

        style.textContent = `
.factorio-api-download {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: relative;
    top: -2px;
    padding: 8.5px 14px;
    margin-left: 6px;
    background: linear-gradient(to bottom, #d4a574, #a68860);
    color: #1a1a1a !important;
    border: 2px solid #8a6f47;
    border-radius: 4px;
    font-family: Arial, sans-serif;
    font-weight: bold;
    font-size: 13px !important;
    line-height: 1.2 !important;
    min-height: 32px;
    box-sizing: border-box;
    white-space: nowrap;
    cursor: pointer;
    text-decoration: none !important;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    flex-shrink: 0;
}

.factorio-api-download:hover:not(.disabled) {
    background: linear-gradient(to bottom, #e5b88a, #b8977a);
    transform: scale(1.05);
}

.factorio-api-download.disabled {
    opacity: 0.7;
    cursor: not-allowed;
    transform: none !important;
}

.factorio-api-download i {
    margin-right: 6px;
    font-size: 12px;
}
`;


        document.head.appendChild(style);
    }

    /* ----------------------------- */
    /*        MOD NAME HELPERS       */
    /* ----------------------------- */

    function extractModNameFromURL() {
        const parts = window.location.pathname.split('/');
        return (parts[1] === 'mod' && parts[2]) ? parts[2] : null;
    }

    function extractModNameFromHref(href) {
        const match = href.match(/^\/mod\/([^?]+)/);
        return match ? match[1] : null;
    }

    /* ----------------------------- */
    /*        BUTTON CREATOR         */
    /* ----------------------------- */

    function createInstallButton(modName, version = null) {
        const btn = document.createElement('a');
        btn.className = 'text-center mr0 factorio-api-download';
        btn.href = '#';

        const icon = document.createElement('i');
        icon.className = 'fa fa-download';
        btn.appendChild(icon);

        const textSpan = document.createElement('span');
        textSpan.textContent = version ? `Install ${version}` : 'Portal Install';
        btn.appendChild(textSpan);

        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            if (btn.classList.contains('disabled')) return;

            btn.classList.add('disabled');
            icon.style.display = 'none';

            const originalText = textSpan.textContent;
            textSpan.textContent = '⌛ Sending...';

            try {
                const endpoint = version
                ? `http://127.0.0.1:5000/api/download/${modName}/${version}`
                : `http://127.0.0.1:5000/api/download/${modName}`;

                const response = await fetch(endpoint);

                if (response.ok) {
                    textSpan.textContent = '✅ Success!';
                } else {
                    textSpan.textContent = '❌ Error';
                }
            } catch {
                textSpan.textContent = '❌ Offline';
            }

            setTimeout(() => {
                btn.classList.remove('disabled');
                textSpan.textContent = originalText;
                icon.style.display = 'inline-block';
            }, 3000);
        });

        return btn;
    }

    /* ----------------------------- */
    /*     MAIN MOD PAGE BUTTON      */
    /* ----------------------------- */

    function injectIntoModPage() {
        const modName = extractModNameFromURL();
        if (!modName) return;

        const section = document.querySelector('.mod-download-section');
        if (!section) return;

        if (section.querySelector('.factorio-api-download')) return;

        const container = section.querySelector('.btn.mod-download-button');
        if (!container) return;

        const btn = createInstallButton(modName);
        container.after(btn);
    }

    /* ----------------------------- */
    /*   VERSION TABLE INJECTION     */
    /* ----------------------------- */

    function injectIntoVersionTable() {
        const modName = extractModNameFromURL();
        if (!modName) return;

        const rows = document.querySelectorAll('tbody tr');
        if (!rows.length) return;

        rows.forEach(row => {

            const downloadCell = row.querySelector('td.p4.text-center');
            if (!downloadCell) return;

            if (downloadCell.querySelector('.factorio-api-download')) return;

            const versionCell = row.querySelector('td');
            if (!versionCell) return;

            const version = versionCell.textContent.trim();
            if (!version) return;

            const officialButton = downloadCell.querySelector('.button-green');
            if (!officialButton) return;

            const btn = createInstallButton(modName, version);
            officialButton.after(btn);
        });
    }

    /* ----------------------------- */
    /*   SEARCH RESULTS INJECTION    */
    /* ----------------------------- */

    function injectIntoSearchResults() {
        const cards = document.querySelectorAll('.panel-inset-lighter.flex-column.p0');

        cards.forEach(card => {

            const downloadSection = card.querySelector('.mod-download-section');
            if (!downloadSection) return;

            if (downloadSection.querySelector('.factorio-api-download')) return;

            const modLink = card.querySelector('a[href^="/mod/"]');
            if (!modLink) return;

            const modName = extractModNameFromHref(modLink.getAttribute('href'));
            if (!modName) return;

            const container = downloadSection.querySelector('.btn.mod-download-button');
            if (!container) return;

            const btn = createInstallButton(modName);
            container.after(btn);
        });
    }

    /* ----------------------------- */
    /*       OBSERVER SUPPORT        */
    /* ----------------------------- */

    function observePage() {
        const observer = new MutationObserver(() => {
            injectIntoModPage();
            injectIntoSearchResults();
            injectIntoVersionTable();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /* ----------------------------- */
    /*           BOOTSTRAP           */
    /* ----------------------------- */

    injectStyles();
    injectIntoModPage();
    injectIntoSearchResults();
    injectIntoVersionTable();
    observePage();

})();
