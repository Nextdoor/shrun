from shrun.version import VERSION

from setuptools import setup, find_packages

setup(
    name='shrun',
    version=VERSION,
    description='shrun yaml-based runner',
    author='Nextdoor Engineering',
    author_email='eng@nextdoor.com',
    packages=find_packages(exclude=['ez_setup']),
    scripts=['bin/shrun'],
    test_suite='tests',
    install_requires=[
        'future>=0.15.2',
        'pyparsing>=2.1.8',
        'pyyaml',
        'six',
        'termcolor>=1.1.0',
    ],
    tests_require=[
        'pytest',
    ],
    url='https://github.com/Nextdoor/shrun'
)
