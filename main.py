from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
# from selenium.webdriver.remote import webdriver
# from selenium.webdriver.common.keys import Keys


class JS:
    HideApp = 'document.getElementById("app-mount").style.display = "None"'


def loadBrowser():
    import os
    import subprocess

    chrome_binary = r"./chrome/bin/chrome.exe"
    chrome_updater = r"./chrome/chrlauncher 2.5.4 (64-bit).exe"
    if not os.path.exists(chrome_binary):
        assert os.path.exists(chrome_updater)
        subprocess.run([chrome_updater])

    capabilities = {
        'browserName': 'chrome',
        "chromeOptions": {
            "binary": chrome_binary
        }
    }

    browser = webdriver.Chrome(desired_capabilities=capabilities)
    browser.set_window_size(400, 800)
    return browser


def loadDiscord(browser):

    browser.get('https://discordapp.com/channels/@me')
    try:
        # Login
        WebDriverWait(browser, timeout=120).until(lambda browser: browser.current_url == "https://discordapp.com/activity")
        print("Discord loaded")
    except TimeoutException:
        print("Time out.")
        browser.quit()
        raise


def styleDiscord(browser):
    browser.execute_script(JS.HideApp)


def main():
    import traceback

    browser = loadBrowser()
    try:
        loadDiscord(browser)
        styleDiscord(browser)
    except Exception:
        traceback.print_exc()
        browser.quit()


if __name__ == '__main__':
    main()
# browser = webdriver.Chrome("./chromedriver.exe")

# assert 'Yahoo' in browser.title


# elem = browser.find_element_by_name('p')  # Find the search box
# elem.send_keys('seleniumhq' + Keys.RETURN)

# browser.quit()
