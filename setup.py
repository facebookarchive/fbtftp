from os import path
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


# Inspired by the example at https://pytest.org/latest/goodpractises.html
class NoseTestCommand(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # Run nose ensuring that argv simulates running nosetests directly
        import nose
        nose.run_exit(argv=['nosetests'])


here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), 'rb') as f:
    long_description = f.read().decode('utf-8')

setup(
    name='fbtftp',
    version='0.1',
    description="A python3 framework to build dynamic TFTP servers",
    long_description=long_description,
    author='Angelo Failla',
    author_email='pallotron@fb.com',
    license='BSD',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX :: Linux"
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.5",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: System :: Boot",
        "Topic :: Utilities",
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
    ],
    keywords='tftp daemon infrastructure provisioning netboot',
    url='https://www.github.com/facebook/fbtftp',
    packages=find_packages(exclude=['tests']),
    tests_require=[
        'nose', 'coverage', 'mock'
    ],
    setup_requires=[
        "flake8"
    ],
    cmdclass={'test': NoseTestCommand},
)
