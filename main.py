import mintapi
import os
import smtplib, ssl
import datetime
import pytz
import logging
import sqlalchemy as db
from sqlalchemy.orm import scoped_session, sessionmaker
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Env Vars
accountNames = os.environ.get('ACCOUNT_NAMES', None)
thresholdValues = os.environ.get('THRESHOLD_VALUES', None)
accountMessages = os.environ.get('ACCOUNT_MESSAGES', None)
accountContacts = os.environ.get('ACCOUNT_CONTACTS', None)
mintEmail = os.environ.get('MINT_EMAIL', None)
mintPassword = os.environ.get('MINT_PASSWORD', None)
mfaToken = os.environ.get('MFA_TOKEN', None)
fromEmail = os.environ.get('FROM_EMAIL', None)
fromEmailPassword = os.environ.get('FROM_EMAIL_PASSWORD', None)
toEmail = os.environ.get('TO_EMAIL', None)
is_prod = os.environ.get('IS_HEROKU', None)

if not is_prod:
    logging.basicConfig(level = logging.INFO)

dirname = os.path.dirname(__file__)
folderName = os.path.join(dirname, 'session')

port = 465  # For SSL
context = ssl.create_default_context()

# new db
engine = db.create_engine(os.environ.get('DATABASE_URL')) #os.getenv("DATABASE_URL")
# db = db.scoped_session(sessionmaker(bind=engine))
con = scoped_session(sessionmaker(bind=engine)) #engine.connect()
metadata = db.MetaData()
money = db.Table(
    'accounts',
    metadata,
    db.Column('name', db.String, primary_key=True),
    db.Column('balance', db.Float),
    db.Column('lastupdated', db.String),
)

names = [name.strip() for name in accountNames.split(";")]
thresholds = [val.strip() for val in thresholdValues.split(";")]
messages = [msg.strip() for msg in accountMessages.split(";")]
numbers = [number.strip() for number in accountContacts.split(";")]

accountsToCheck = []
for i in range(len(names)):
    accountsToCheck += [(
    names[i],
    float(thresholds[i]),
    messages[i],
    numbers[i])]

def updateAccountToDB(name, amount, new):
    timestamp = datetime.datetime.now(tz=pytz.timezone('America/Los_Angeles')).strftime('%Y-%m-%d %H:%M:%S')
    logging.info('Inserting balance {} for {}'.format(amount, name))
    if new:
        query = db.insert(money).values(name=name, balance=amount, lastupdated=timestamp)
    else:
        query = db.update(money).values(balance=amount).where(money.columns.name == name)
    con.execute(query)
    con.commit()

def getAccountBalanceFromDB(name):
    logging.info('Getting balance for account: {}'.format(name))
    query = db.select([money]).where(money.columns.name == name)
    result = con.execute(query)
    for row in result:
        logging.info(row)
        return row[1]

def mintLogin():
    logging.info('Logging in to Mint account')
    return mintapi.Mint(
    mintEmail,  # Email used to log in to Mint
    mintPassword,  # Your password used to log in to mint
    # Optional parameters
    mfa_method='soft-token',  # Can be 'sms' (default), 'email', or 'soft-token'.
                       # if mintapi detects an MFA request, it will trigger the requested method
                       # and prompt on the command line.
    mfa_token=mfaToken,
    headless=True,  # Whether the chromedriver should work without opening a
                     # visible window (useful for server-side deployments)
    mfa_input_callback=None,  # A callback accepting a single argument (the prompt)
                              # which returns the user-inputted 2FA code. By default
                              # the default Python `input` function is used.
    session_path=None, # Directory that the Chrome persistent session will be written/read from.
                       # To avoid the 2FA code being asked for multiple times, you can either set
                       # this parameter or log in by hand in Chrome under the same user this runs
                       # as.
    imap_account=None, # account name used to log in to your IMAP server
    imap_password=None, # account password used to log in to your IMAP server
    imap_server=None,  # IMAP server host name
    imap_folder='INBOX',  # IMAP folder that receives MFA email
    wait_for_sync=True,  # do not wait for accounts to sync
    wait_for_sync_timeout=300,  # number of seconds to wait for sync
    use_chromedriver_on_path=False,  # True will use a system provided chromedriver binary that
                                     # is on the PATH (instead of downloading the latest version)
    )


def getAccountBalanceFromMint(name, accounts):
    logging.info('Getting account with name: {}'.format(name))
    for account in accounts:
        if account['accountName'] == name:
            return account['currentBalance']

def sendEmail(accountName, fromEmail, password, toEmail, message, number):
    # code from https://realpython.com/python-send-email/#option-1-setting-up-a-gmail-account-for-development
    html = """\
    <html>
      <body>
        <p>Hi,<br>
           {}<br>
    """.format(message)

    if number != "":
        html +="""\
        Contact us at <a href="tel:{}">{}</a>
        """.format(number.strip('-'), number)

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
        logging.info('Logging into email: {}'.format(fromEmail))
        server.login(fromEmail, password)
        server.sendmail(fromEmail, toEmail, processedMessage.as_string())


mint = mintLogin()
accounts = mint.get_accounts()
mint.close()

for account in accountsToCheck:
    name = account[0]
    threshold = account[1]
    message = account[2]
    number = account[3]

    accountOldBalance = getAccountBalanceFromDB(name)
    accountNewBalance = getAccountBalanceFromMint(name, accounts)

    if not accountNewBalance:
        raise ValueError('Cannot get balance from Mint')

    logging.info('New balance: {}'.format(accountNewBalance))

    if not accountOldBalance:
        updateAccountToDB(name, accountNewBalance, True)
        continue
    else:
        updateAccountToDB(name, accountNewBalance, False)

    if (accountNewBalance - accountOldBalance) >= float(threshold):
        sendEmail(name, fromEmail, fromEmailPassword, toEmail, message, number)

sendEmail('test', fromEmail, fromEmailPassword, fromEmail, 'ran successfully', '')
