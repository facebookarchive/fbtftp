# How to contribute

Contributing to `fbtftp` follows the same process of contributing to any GitHub
repository. In short:

* forking the project
* making your changes
* making a pull request

More details in the following paragraphs.

# Prerequisites

In order to contribute to `fbtftp` you need a GitHub account. If you don't have
one already, please [sign up on GitHub](https://github.com/signup/free) first.

# Making your changes

To make changes you have to:

* fork the `fbtftp` repository. See [Fork a
 repo](https://help.github.com/articles/fork-a-repo/) on GitHub's documentation
* make your changes locally. See Coding Style below
* make a pull request. See [Using pull
requests](https://help.github.com/articles/using-pull-requests/) on GitHub's
documentation

Once we receive your pull request, one of our project members will review your
changes, if necessary they will ask you to make additional changes, and if the
patch is good enough, it will be merged in the main repository.

# Coding style

`fbtftp` is written in Python 3 and follows the
[PEP-8 Style Guide](https://www.python.org/dev/peps/pep-0008/) plus some
Facebook specific style guids. We want to keep the style consistent throughout
the code, so we will not accept pull requests that do not pass the style
checks.  The style checking is done when running `make test`, please make sure
to run it before submitting your patch.

You might also consider installing and using `yapf` to automatically format
the code to follow our style guidelines. A `.style.yapf` is provided to
facilitate this.

Run this before you send your PR:
```
$ pip3 install yapf
$ make clean
$ yapf -i $(find . -name ".py")
```

# I don't want to make a pull request!

We love pull requests, but it's not necessary to write code to contribute. If
for any reason you can't make a pull request (e.g. you just want to suggest us
an improvement), let us know.
[Create an issue](https://help.github.com/articles/creating-an-issue/)
on the `fbtftp` issue tracker and we will review your request.


# Code of Conduct

Facebook has adopted a Code of Conduct that we expect project participants to adhere to. Please [read the full text](https://code.facebook.com/codeofconduct) so that you can understand what actions will and will not be tolerated.
