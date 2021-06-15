
from setuptools import setup, find_packages

with open("PROJECT_DESCRIPTION.md", "r") as fh:
    long_description = fh.read()

setup(
    name='dynamite-nsm',
    version='0.8.0',
    packages=find_packages(),
    scripts=['scripts/dynamite'],
    url='http://dynamite.ai',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='GPL 3',
    author='Jamin Becker',
    author_email='jamin@dynamite.ai',
    description='DynamiteNSM is an network security monitor with an emphasis on very fast deployment, '
                'minimal configuration, and intuitive management.',
    include_package_data=True,
    install_requires=[
        'coloredlogs==15.0',
        'progressbar==2.5',
        'tabulate==0.8.9',
        'PyYAML==5.3.1',
        'npyscreen==4.10.5',
        'psutil==5.8.0',
        'docstring-parser==0.7.3',
        'marshmallow==3.11.1',
        'pytest==6.2.2',
        'python-daemon==2.3.0',
        'requests==2.24.0',
        'sqlalchemy==1.3.18',
        'Unidecode==1.2.0',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Operating System :: POSIX :: Linux',
        'Environment :: Console',
        'Topic :: System :: Networking :: Monitoring',
        'Topic :: Security'
    ]
)
