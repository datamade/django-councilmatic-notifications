import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-councilmatic-notifications',
    version='2.5.1',
    packages=['notifications'],
    include_package_data=True,
    license='MIT License',  # example license
    description='Core functions for councilmatic.org family',
    long_description=README,
    url='http://councilmatic.org/',
    author='DataMade, LLC',
    author_email='info@datamade.us',
    install_requires=[
        'django-councilmatic>=2.5.4',
        'django-rq>=0.9.3',
        'django-password-reset>=2.0'
    ],
    extras_require={'tests': ['pytest', 'pytest-django', 'pytest-mock']},
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',  # example license
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        # Replace these appropriately if you are stuck on Python 2.
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
