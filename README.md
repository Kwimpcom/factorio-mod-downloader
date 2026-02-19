# Factorio Mod Downloader
This is a direct fork of [FactorioModPortal](https://github.com/MRtecno98/FactorioModPortal) by [MRtecno98](https://github.com/MRtecno98) that adds browser integration for ease of use.

# Usage

*You need to install the requirements with pip/pip3 with the code below :* 

```bash
  pip install -r requirements.txt
```

You can use this to directly download and install a mod

```bash
  python fmd.py install krastorio2 # you can use both mod id or URLs
```

Or 

```bash
  python fmd.py
```

To just use the TUI.

# Using Browser Integration

You need to first start the server in the background :

```bash
  python fmd.py start-server
```

In this situation, I decided to use an userscript instead of a whole extension since it's a hassle.<br>
You first need to use Tampermonkey or Violentmonkey or anything else to use the browser integration feature which you can get here:

[Tampermonkey for Chrome](https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo?hl=en)<br>

[Tampermonkey for Firefox](https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/)

After that, you can install the userscript for the browser integration from here:

[factorio-mod-downloader-1.0.0.user.js](https://github.com/Kwimpcom/factorio-mod-downloader/raw/refs/heads/master/userscripts/factorio-mod-downloader-1.0.0.user.js)

After installation you can just visit a mod's page or the search and see the "Portal Install" button.


