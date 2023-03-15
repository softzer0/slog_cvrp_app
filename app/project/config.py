from os import getenv

class Config(object):
    SQLALCHEMY_DATABASE_URI = getenv('DATABASE_URI', 'sqlite://')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    SQLALCHEMY_ECHO = True