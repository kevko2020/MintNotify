from mint_api_update import Mint
from account import Account
import os
import smtplib, ssl
import datetime
import pytz
import logging
import sqlalchemy as db
from sqlalchemy.orm import scoped_session, sessionmaker
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

# Env Vars
# Required
mintEmail = os.environ.get("MINT_EMAIL", "email")
mintPassword = os.environ.get("MINT_PASSWORD", "password")
mfaToken = os.environ.get("MFA_TOKEN", "token")

# Optional
accountNames = os.environ.get("ACCOUNT_NAMES", "")
thresholdValues = os.environ.get("THRESHOLD_VALUES", "")
accountMessages = os.environ.get("ACCOUNT_MESSAGES", "")
accountContacts = os.environ.get("ACCOUNT_CONTACTS", "")
fromEmail = os.environ.get("FROM_EMAIL")
fromEmailPassword = os.environ.get("FROM_EMAIL_PASSWORD")
toEmail = os.environ.get("TO_EMAIL")
is_prod = os.environ.get("IS_HEROKU", False)

# Crypto
# TODO: add support for wallet addresses
cryptoNames = os.environ.get("CRYPTO_NAMES", "BTC;ETH")
cryptoAmounts = os.environ.get("CRYPTO_AMOUNTS", "0.1;1")

if not is_prod:
    logging.basicConfig(level=logging.INFO)

dirname = os.path.dirname(__file__)
folderName = os.path.join(dirname, "session")

port = 465  # For SSL
context = ssl.create_default_context()

# db setup
engine = db.create_engine(os.environ.get("DATABASE_URL", "postgres://kko@/money"))
con = scoped_session(sessionmaker(bind=engine))

metadata = db.MetaData()
money = db.Table(
    "accounts",
    metadata,
    db.Column("name", db.String, primary_key=True),
    db.Column("balance", db.Float),
    db.Column("lastupdated", db.String),
)

names = [name.strip() for name in accountNames.split(";")]
thresholds = [val.strip() for val in thresholdValues.split(";")]
messages = [msg.strip() for msg in accountMessages.split(";")]
numbers = [number.strip() for number in accountContacts.split(";")]
cryptoNames = [name.strip() for name in cryptoNames.split(";")]
cryptoAmounts = [amount.strip() for amount in cryptoAmounts.split(";")]

accountsToCheck = []
for i in range(len(names)):
    if names[i]:
        accountsToCheck += [
            Account(names[i], float(thresholds[i]), messages[i], numbers[i])
        ]

cryptos = {}
for i in range(len(cryptoNames)):
    name = cryptoNames[i]
    amount = cryptoAmounts[i]
    cryptos[name] = float(amount)


def updateAccountToDB(name, amount, new):
    timestamp = datetime.datetime.now(tz=pytz.timezone("America/Los_Angeles")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    logging.info("Inserting balance {} for {}".format(amount, name))
    if new:
        query = db.insert(money).values(
            name=name, balance=amount, lastupdated=timestamp
        )
    else:
        query = (
            db.update(money)
            .values(balance=amount, lastupdated=timestamp)
            .where(money.columns.name == name)
        )
    con.execute(query)
    con.commit()


def getAccountBalanceFromDB(name):
    logging.info("Getting balance for account: {}".format(name))
    query = db.select([money]).where(money.columns.name == name)
    result = con.execute(query)
    for row in result:
        logging.info(row)
        return row[1]


def mintLogin():
    logging.info("Logging in to Mint account")
    return Mint(
        mintEmail,  # Email used to log in to Mint
        mintPassword,  # Your password used to log in to mint
        # Optional parameters
        mfa_method="soft-token",  # Can be 'sms' (default), 'email', or 'soft-token'.
        # if mintapi detects an MFA request, it will trigger the requested method
        # and prompt on the command line.
        mfa_token=mfaToken,
        headless=True,  # Whether the chromedriver should work without opening a
        # visible window (useful for server-side deployments)
        mfa_input_callback=None,  # A callback accepting a single argument (the prompt)
        # which returns the user-inputted 2FA code. By default
        # the default Python `input` function is used.
        session_path=None,  # Directory that the Chrome persistent session will be written/read from.
        # To avoid the 2FA code being asked for multiple times, you can either set
        # this parameter or log in by hand in Chrome under the same user this runs
        # as.
        imap_account=None,  # account name used to log in to your IMAP server
        imap_password=None,  # account password used to log in to your IMAP server
        imap_server=None,  # IMAP server host name
        imap_folder="INBOX",  # IMAP folder that receives MFA email
        wait_for_sync=True,  # do not wait for accounts to sync
        wait_for_sync_timeout=600,  # number of seconds to wait for sync
        use_chromedriver_on_path=True,  # True will use a system provided chromedriver binary that
        # is on the PATH (instead of downloading the latest version)
    )

def getAccountBalanceFromMint(name, accounts):
    logging.info("Getting account with name: {}".format(name))
    for account in accounts:
        if account["accountName"] == name:
            return account["currentBalance"]


# need to update since gmail has blocked this.
def sendEmail(accountName, fromEmail, password, toEmail, message, number):
    # code from https://realpython.com/python-send-email/#option-1-setting-up-a-gmail-account-for-development
    html = """\
    <html>
      <body>
        <p>Hi,<br>
           {}<br>
    """.format(
        message
    )

    if number != "":
        html += """\
        Contact us at <a href="tel:{}">{}</a>
        """.format(
            number.strip("-"), number
        )

    html += """\
        </p>
      </body>
    </html>
    """

    processedMessage = MIMEMultipart("alternative")
    processedMessage.attach(MIMEText(html, "html"))
    processedMessage["Subject"] = "{} Contribution Completed".format(accountName)
    processedMessage["From"] = fromEmail
    processedMessage["To"] = toEmail

    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        logging.info("Logging into email: {}".format(fromEmail))
        server.login(fromEmail, password)
        server.sendmail(fromEmail, toEmail, processedMessage.as_string())


def getCryptoPrice(crypto):
    URL = "https://api.coinbase.com/v2/prices/{}-USD/spot".format(crypto)

    r = requests.get(url=URL)
    data = r.json()

    return float(data["data"]["amount"])


def updateCrypto(cryptos):
    for name, amount in cryptos.items():
        for account in accounts:
            if account["accountName"] == name:
                mint.set_property_account_value(account, getCryptoPrice(name) * amount)
                break


def checkAccounts(accounts):
    for account in accountsToCheck:
        name = account.getName()
        threshold = account.getThreshold()
        message = account.getMessage()
        number = account.getNumber()

        accountOldBalance = getAccountBalanceFromDB(name)
        accountNewBalance = getAccountBalanceFromMint(name, accounts)

        if not accountNewBalance:
            raise ValueError("Cannot get balance from Mint")

        logging.info("New balance: {}".format(accountNewBalance))

        if not accountOldBalance:
            updateAccountToDB(name, accountNewBalance, True)
            continue
        else:
            updateAccountToDB(name, accountNewBalance, False)

        if (accountNewBalance - accountOldBalance) >= float(threshold):
            try:
                sendEmail(name, fromEmail, fromEmailPassword, toEmail, message, number)
            except Exception:
                logging.error('Failed to log in')


# Login and check accounts
mint = mintLogin()

logging.info('Getting account info from mint...')
accounts = mint.get_accounts()

logging.info('Checking account for changes...')
checkAccounts(accounts)

# Update crypto
logging.info('Updating crypto...')
updateCrypto(cryptos)

# Close connection
mint.close()
