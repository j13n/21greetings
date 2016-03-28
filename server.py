import os, re
from datetime import datetime
from threading import Thread
from flask import Flask, url_for, jsonify, request, render_template
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.migrate import Migrate, MigrateCommand
from flask.ext.mail import Mail, Message

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
manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)
mail = Mail(app)

### Send e-mail asynchronously:
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

### Command to generate greeting cards, new greeting cards can be added later:
@manager.command
def create_cards():
    db.create_all()
    from sqlalchemy.exc import IntegrityError
    GREETING_CARDS = (
        ['Greeting card with a theme for general messages.', 'general'],
        ['Greeting card with a theme for romantic messages.', 'iloveyou'],
        ['Greeting card with a theme for birthday messages.', 'birthday'])
    for g in GREETING_CARDS:
        card = GreetingCard.query.filter_by(template=g[1]).first()
        if card is None:
            card = GreetingCard(description=g[0], template=g[1])
            db.session.add(card)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()

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

### Models:
class GreetingCard(db.Model):
    __tablename__ = "greetingcards"
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, unique=True)
    template = db.Column(db.String(64), unique=True)
    greetings = db.relationship('Greeting', backref='greetingcards', lazy='dynamic')

    def get_url(self):
        return url_for('get_greeting_card', id=self.id, _external=True)

    def export_data(self):
        return {
            'description': self.description,
            'template': self.template,
            'self_url': self.get_url()
            }

class Greeting(db.Model):
    __tablename__ = 'greetings'
    id = db.Column(db.Integer, primary_key=True)
    greeting_card = db.Column(db.Integer, db.ForeignKey('greetingcards.id'))
    title = db.Column(db.String(128))
    message = db.Column(db.String(512))
    email = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_url(self):
        return url_for('greeting', id=self.id, _external=True)

    def export_data(self):
        return {
        'greeting_card': self.greeting_card,
        'created_at': self.created_at,
        'self_url': self.get_url()
        }

    def import_data(self, data):
        try:
            '''
            This is the only function that actually imports external / user
            data. Since you should never trust external input, regular
            expressions are used to remove all but alphanumeric and underscore
            characters and a (lenient) check whether a valid e-mail adres was used.
            '''
            self.greeting_card = data['greeting_card']
            self.title = re.sub(r'\W', ' ', data['title'])
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
@app.route('/greetingcards/', methods=['GET'])
def get_greeting_cards():
    return jsonify({'greetingcards': [greeting_card.get_url() for greeting_card
                                        in GreetingCard.query.all()]})

@app.route('/greetingcard/<int:id>', methods=['GET'])
def get_greeting_card(id):
    return jsonify(GreetingCard.query.get_or_404(id).export_data())

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
    template = GreetingCard.query.filter_by(id=greeting.greeting_card).first().template
    msg = Message(subject='You have received a Bitcoin powered greeting!',
                    sender='greeting@21projects.xyz', recipients=[greeting.email])
    msg.body = render_template(template + '.txt', title=greeting.title, message=greeting.message)
    msg.html = render_template(template + '.html', title=greeting.title, message=greeting.message)
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return jsonify({'Location': greeting.get_url()}), 201

if __name__ == '__main__':
    manager.run()
