import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-councilmatic-notifications',
    version='0.1.27',
    packages=['notifications'],
    include_package_data=True,
    license='MIT License',  # example license
    description='Core functions for councilmatic.org family',
    long_description=README,
    url='http://councilmatic.org/',
    author='DataMade, LLC',
    author_email='info@datamade.us',
    install_requires=[
        'django-councilmatic>=0.7,<=0.8.7',
        'rq>=0.5.5,<1.0',
        'django-rq==0.9.3'
    ],
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
