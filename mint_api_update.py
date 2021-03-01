import json
import logging

import mintapi
from lxml import html

MINT_OVERVIEW_URL = "https://mint.intuit.com/overview.event"
PROPERTY_ACCOUNT_URL_FORMAT = "https://mint.intuit.com/mas/v1/providers/PFM:{}_{}/accounts/PFM:OtherPropertyAccount:{}_{}"


class Mint(mintapi.Mint):
    browser_auth_api_key = None
    mint_user_id = None
    cookie = None

    def login_and_get_token(self, email, password, mfa_method, mfa_token, **args):
        super().login_and_get_token(email, password, mfa_method, mfa_token, **args)

        doc = html.document_fromstring(self.get(MINT_OVERVIEW_URL).text)
        self.mint_user_id = json.loads(doc.get_element_by_id("javascript-user").value)[
            "userId"
        ]
        self.get_api_key_header()
        self.get_session_cookies()

    def patch(self, url, **kwargs):
        return self.driver.request("PATCH", url, **kwargs)

    def get_session_cookies(self):
        self.cookie = self.driver.get_cookie("mint.intuit.com")
        return

    def get_api_key_header(self):
        key_var = "window.MintConfig.browserAuthAPIKey"
        api_key = self.driver.execute_script("return " + key_var)
        self.browser_auth_api_key = api_key
        return api_key

    def set_property_account_value(self, account, value):
        account_id = account["accountId"]
        account_login_id = account["fiLoginId"]
        account_update_url = PROPERTY_ACCOUNT_URL_FORMAT.format(
            self.mint_user_id, account_login_id, self.mint_user_id, account_id
        )

        r = self.patch(
            account_update_url,
            json={
                "name": account["accountName"],
                "value": value,
                "type": "OtherPropertyAccount",
            },
            headers={
                "authorization": "Intuit_APIKey intuit_apikey={}, intuit_apikey_version=1.0".format(
                    self.browser_auth_api_key
                ),
                "content-type": "application/json",
                "cookie": self.cookie,
            },
        )

        if not r.ok:
            logging.error("Could not update mint for {}".format(account))
