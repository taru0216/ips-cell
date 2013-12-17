SUBDIRS = examples

EXTRA_DIST = \
    common tests servers tools setup.py debian/ README.md ips-cell.spec \
    .project .pydevproject bootstrap

# TODO(masato.taruishi) Make this configurable
PYTHON_INSTALL_OPTS = --install-layout=deb

PROTOS = $(shell find $(srcdir)/common -name '*.proto')
TESTS = tests/test.sh
TESTS_ENVIRONMENT = /usr/bin/env abs_builddir=$(abs_builddir) srcdir=$(srcdir)

noinst_DATA = python.stamp

python.stamp: gen/ips/proto/__init__.py
	srcdir=$(srcdir) $(PYTHON) $(srcdir)/setup.py build --force
	touch $@

gen/ips/proto/__init__.py: $(srcdir)/common/proto/ips/proto/__init__.py
	install -d gen/ips/proto/
	for p in $(PROTOS); do protoc -I$(srcdir)/common/proto $$p \
	    --python_out=gen || exit 1; done
	cp $(srcdir)/common/proto/ips/proto/__init__.py \
	    gen/ips/proto/__init__.py

buildinfo: Makefile
	echo "build-timestamp: $(shell date +%s)" > $@

install-data-local: buildinfo
	srcdir=$(srcdir) $(PYTHON) $(srcdir)/setup.py install --force \
	    --root=$(DESTDIR) --no-compile -O0 $(PYTHON_INSTALL_OPTS)
	install -d $(DESTDIR)/srv/ips/users
	install -d $(DESTDIR)/usr/share/ips-common/ips/proto/
	install -d $(DESTDIR)/var/lib/ips-cell/sandbox/archive/
	install -m644 $(srcdir)/common/proto/ips/proto/*.proto \
	    $(DESTDIR)/usr/share/ips-common/ips/proto/
	install -d $(DESTDIR)/usr/share/lxc/templates/
	install -m755 $(srcdir)/servers/cell/lxc-ips-archive \
	    $(DESTDIR)/usr/share/lxc/templates/

deb:
	debuild -b -us -uc

rpm: dist
	rpmbuild -ta $(DIST_ARCHIVES)

deb-release: import
	git-buildpackage --git-pbuilder -sa
	git-buildpackage --git-pbuilder -sa --git-tag
	debsign

import:
	git checkout develop
	./bootstrap
	./configure
	make dist
	make distclean
	/bin/rm -rf \
	    Makefile.in \
	    aclocal.m4 \
	    configure \
	    examples/Makefile.in \
	    install-sh \
	    missing \
	    autom4te.cache/

	git checkout upstream
	-git tag -d upstream/$(VERSION)
	mv $(distdir).tar.gz ..
	-mv ../$(PACKAGE)_$(VERSION).orig.tar.gz /tmp/
	git-import-orig ../ips-cell-0.tar.gz

	git checkout master
	git-dch -a -R --git-author
	git commit -a -m 'Updated the changelog for the new release'

clean-local:
	srcdir=$(srcdir) $(PYTHON) $(srcdir)/setup.py clean
	/bin/rm -rf python.stamp gen/ *.egg-info/ build/ buildinfo
	find . -name '*.pyc' | xargs /bin/rm -f
