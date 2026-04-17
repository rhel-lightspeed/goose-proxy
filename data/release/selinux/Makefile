# Taken and updated from https://github.com/freeipa/freeipa/blob/release-4-12-2/selinux/Makefile.am
SELINUXTYPE = targeted
NULL =

MODULE_NAME = goose_proxy
MODULE = $(MODULE_NAME).pp.bz2
MODULE_IF = $(MODULE_NAME).if

dist_noinst_DATA =				\
	$(MODULE_NAME).fc			\
	$(MODULE_NAME).if			\
	$(MODULE_NAME).te			\
	$(NULL)

selinuxpolicydir = $(datarootdir)/selinux/packages/$(SELINUXTYPE)
nodist_selinuxpolicy_DATA =	    \
	$(MODULE)					\
	$(NULL)

selinux_makefile = /usr/share/selinux/devel/Makefile

%.pp.bz2: %.pp
	bzip2 -f -9 $^

%.pp: %.te %.fc %.if
	make -f $(selinux_makefile) $@

.PHONY: clean-local
clean-local:
	rm -rf *~  *.tc *.pp *.pp.bz2 tmp *.cil *.8

.PHONY: test
test: $(MODULE_NAME).pp
	# https://access.redhat.com/articles/6999267
	sudo semodule -i $(MODULE_NAME).pp

%.cil: %.pp
	cat $(MODULE_NAME).pp | /usr/libexec/selinux/hll/pp > $(MODULE_NAME).cil

.PHONY: man
man:
	sepolicy manpage -p . -d $(MODULE_NAME)_t