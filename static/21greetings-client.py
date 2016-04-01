import requests, json, sys
from flask import Flask, render_template, flash, redirect, url_for
from flask.ext.script import Manager
from flask.ext.bootstrap import Bootstrap
from flask.ext.wtf import Form
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from flask.ext.wtf.html5 import EmailField
from wtforms.validators import Required, Length, Email

# import from 21 Bitcoin Developer Library
from two1.commands.config import Config
from two1.lib.wallet import Wallet
from two1.lib.bitrequests import BitTransferRequests

app = Flask(__name__, template_folder="../templates")
manager = Manager(app)
bootstrap = Bootstrap(app)
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = 'a_very-long_password-here'

wallet = Wallet()
username = Config().username

class GreetingForm(Form):
    message = TextAreaField(
        validators=[Required(message='A greeting is required..'), Length(min=1, max=1024)])
    email = EmailField(
        validators=[Required(message='An email is required..'), Email(message='A valid e-mail is required.')])
    submit = SubmitField('Happy Birthday!')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = GreetingForm()
    if form.validate_on_submit():
        bit_transfer_request = BitTransferRequests(wallet, username)
        json = {
            'message': form.message.data,
            'email': form.email.data
        }
        headers = {
            'Content-Type': 'application/json'
        }
        response = bit_transfer_request.post(url='http://localhost:8080/greeting/', headers=headers, json=json)
        if response.status_code != 201:
            flash('An error occured: {}, statuscode: {}'.format(response, response.status_code))
            return redirect(url_for('.index'))
        else:
            flash('Your Birthday message was sent to: {}'.format(form.email.data))
            return redirect(url_for('.index'))
    else:
        for field, errors in form.errors.items():
            flash('Error in the {} field: {}'.format(getattr(form, field).label.text, errors))
    return render_template('base.html', form=form)


# request the bitcoin-enabled endpoint you're hosting on the 21 Bitcoin Computer
@manager.option('-m', '--message', dest='message', help='Enter your message')
@manager.option('-e', '--email', dest='email', help='Recipient of greeting card')
def send(message, email):
    bit_transfer_requests = BitTransferRequests(wallet, username)
    json = {
        'message': message,
        'email': email
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = bit_transfer_requests.post(url='http://localhost:8080/greeting/', headers=headers, json=json)
    if response.status_code != 201:
        print(response.text)
        sys.exit()
    print(response.text)

if __name__ == '__main__':
    manager.run()
