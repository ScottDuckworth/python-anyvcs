import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

exec(open('anyvcs/version.py').read())

setup(
    name='anyvcs',
    version=__version__,
    packages=['anyvcs'],
    include_package_data=True,
    license='BSD',
    description='An abstraction layer for multiple version control systems.',
    long_description=README,
    url='https://github.com/ScottDuckworth/python-anyvcs',
    author='Scott Duckworth',
    author_email='sduckwo@clemson.edu',

    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Version Control',
    ],
)

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
