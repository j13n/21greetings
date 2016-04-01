import os, re
from datetime import datetime
from threading import Thread
from flask import Flask, url_for, jsonify, request, render_template, abort
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.mail import Mail, Message

### import from the 21 Bitcoin Developer Library
from two1.lib.wallet import Wallet
from two1.lib.bitserv.flask import Payment

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'data.sqlite')

### Instanciate app and set configurations:
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['DEBUG'] = True
app.config['MAIL_SERVER'] = 'mail.privateemail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

### Instanciate modules:
wallet = Wallet()
payment = Payment(app, wallet)
db = SQLAlchemy(app)
mail = Mail(app)

### Send e-mail asynchronously:
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

### Error handlers:
class ValidationError(ValueError):
    pass

@app.errorhandler(ValidationError)
def bad_request(e):
    response = jsonify({'status': 400, 'error': 'bad request',
                        'message': e.args[0]})
    response.status_code = 400
    return response

@app.errorhandler(404)
def not_found(e):
    response = jsonify({'status': 404, 'error': 'not found',
                        'message': 'invalid resource URI'})
    response.status_code = 404
    return response

@app.errorhandler(405)
def method_not_supported(e):
    response = jsonify({'status': 405, 'error': 'method not supported',
                        'message': 'the method is not supported'})
    response.status_code = 405
    return response

@app.errorhandler(500)
def internal_server_error(e):
    response = jsonify({'status': 500, 'error': 'internal server error',
                        'message': e.args[0]})
    response.status_code = 500
    return response

class Greeting(db.Model):
    __tablename__ = 'greetings'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    email = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_url(self):
        return url_for('greeting', id=self.id, _external=True)

    def export_data(self):
        '''
        This is the function to export data. To respect user's privacy I decided
        not to return the actual messages themselves.
        '''
        return {
        'created_at': self.created_at,
        'self_url': self.get_url()
        }

    def import_data(self, data):
        try:
            '''
            This is the only function that actually imports external / user
            data. Since you should never trust external input, regular
            expression is used to remove all but alphanumeric and underscore
            characters and a (lenient) check whether a valid e-mail adres was used.
            '''
            try:
                re.match(r'\w{1-1024}')
            except:
                raise ValidationError('Message is to short or to long, maximum of 1024 characters is allowed.')
                abort()
            self.message = re.sub(r'\W', ' ', data['message'])
            try:
                re.match(r'[^@]+@[^@]+\.[^@]+', data['email'])
            except KeyError as e:
                ValidationError('Invalid E-mail Address: ' + e.args[0])
            self.email = data['email']
        except KeyError as e:
            raise ValidationError('Invalid Greeting Card: missing ' + e.args[0])
        return self

### Routes:
@app.route('/greetings/', methods=['GET'])
def greetings():
    return jsonify({'greetings': [greetings.get_url() for greetings
                                    in Greeting.query.all()]})

@app.route('/greeting/<int:id>', methods=['GET'])
def greeting(id):
    '''
    This is the function to view individual greetings that were send. Because
    this API is available to the public and messages should be private the
    export_data function only exports the greeting card type and date sent.
    '''
    return jsonify(Greeting.query.get_or_404(id).export_data())

@app.route('/greeting/', methods=['POST'])
@payment.required(1000)
def new_greeting():
    '''
    This is the only route where a POST method is allowed. First the request is
    validated and a database entry is created. Then the e-mail is created and
    send to a different thread to increase responsiveness.
    '''
    greeting = Greeting()
    greeting.import_data(request.json)
    db.session.add(greeting)
    db.session.commit()
    msg = Message(subject='You have received a 21 / Bitcoin powered Birtday greeting!',
                    sender='greeting@21projects.xyz', recipients=[greeting.email])
    msg.body = render_template('birthday.txt', message=greeting.message)
    msg.html = render_template('birthday.html', message=greeting.message)
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return jsonify({'Location': greeting.get_url()}), 201

@app.route('/manifest')
def docs():
    '''
    Serves the app manifest to the 21 crawler.
    '''
    with open('manifest.yaml', 'r') as f:
        manifest_yaml = yaml.load(f)
    return json.dumps(manifest_yaml)

@app.route('/client')
def client():
    '''
    Provides an example client script.
    '''
    return send_from_directory('static', '21greetings-client.py')

if __name__ == '__main__':
    db.create_all()
    app.run(port=8080)
