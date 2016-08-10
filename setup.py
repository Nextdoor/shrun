from flaml.version import VERSION

from setuptools import setup, find_packages

setup(
    name='flaml',
    version=VERSION,
    description='flaml yaml-based runner',
    author='Dev Tools Team',
    author_email='asbrown@nextdoor.com',
    packages=find_packages(exclude=['ez_setup']),
    scripts=['bin/flaml'],
    test_suite='tests',
    install_requires=[
        'future>=0.15.2',
        'pyyaml',
    ],
    tests_require=[
        'pytest',
    ],
    url='https://https://git.corp.nextdoor.com/Nextdoor/flaml'
)
