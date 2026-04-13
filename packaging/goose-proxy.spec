# Set selinux_ver depending on RHEL version
%define selinux_ver 38.1.65

%if 0%{?rhel} && 0%{?rhel} > 10
%define selinux_ver 42.1.7
%endif

%define selinuxtype targeted
%define modulename goose_proxy

Name:           goose-proxy
Version:        0.1.0
Release:        %autorelease
Summary:        A proxy API for RHEL command line assistant

License:        Apache-2.0
URL:            https://github.com/rhel-lightspeed/goose-proxy
Source:         %{url}/archive/v%{version}/goose-proxy-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  tomcli

# Build dependencies
BuildRequires:  python3-devel
BuildRequires:  systemd-units

# Test dependencies
BuildRequires:  python3-pytest
BuildRequires:  python3-pytest-asyncio

# Docs dependencies
# Sphinx is used to build the manpages for the project.
BuildRequires:  python3-sphinx

# SELinux policy build dependencies
BuildRequires:  selinux-policy-devel
BuildRequires:  bzip2

# Add selinux subpackage as dependency
Requires:       %{name}-selinux


%description
A lightweight API translation proxy that bridges Goose with backend servers
that speak the Responses API from OpenAI, such as Lightspeed Stack.

%prep
%autosetup -p1

# Remove options from pytest as some of them are not available in Fedora at all
tomcli set pyproject.toml del tool.pytest.ini_options.addopts

# Swap the dynamic version property to version property, as we are pulling
# sources from github and not a pypi distribution release.
tomcli set pyproject.toml del project.dynamic
tomcli set pyproject.toml str project.version "%{version}"

# Drop extras from fastapi as standard-no-fastapi-cloud-cli is not available as
# an extra in Fedora.
tomcli set pyproject.toml arrays replace project.dependencies 'fastapi\[standard-no-fastapi-cloud-cli\](.*)' 'fastapi\1'

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

# Build the manpages
sphinx-build -b man docs/man docs/build/man

# Build SELinux policy module
%{__make} -C data/release/selinux %{modulename}.pp.bz2

%install
%pyproject_install
%pyproject_save_files -l goose_proxy

# Install the manpages for goose-proxy and goose-proxy-config
%{__install} -D -m 0644 docs/build/man/%{name}-config.5 %{buildroot}%{_mandir}/man5/%{name}-config.5
%{__install} -D -m 0644 docs/build/man/%{name}.7 %{buildroot}%{_mandir}/man7/%{name}.7

# System units
%{__install} -D -m 0644 data/release/systemd/%{name}.service %{buildroot}/%{_unitdir}/%{name}.service

# Config file
%{__install} -d -m 0700 %{buildroot}/%{_sysconfdir}/xdg/%{name}
%{__install} -D -m 0600 data/release/xdg/config.toml %{buildroot}/%{_sysconfdir}/xdg/%{name}/config.toml

# Red Hat specific configs
# Install the goose-init shell script inside /etc/profile.d for automatic
# placement of the goose-config and custom_goose-proxy on user home directory.
%{__install} -Dpm 0755 data/release/goose/goose-init.sh %{buildroot}%{_sysconfdir}/profile.d/goose-init.sh 
	
# Install the sources into /usr/share/goose-redhat
%{__install} -Dpm 0644 data/release/goose/config.yaml  %{buildroot}%{_datadir}/goose-redhat/config.yaml 
%{__install} -Dpm 0644 data/release/goose/custom_goose-proxy.json %{buildroot}%{_datadir}/goose-redhat/custom_goose-proxy.json 

# SELinux policy module
%{__install} -d %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}
%{__install} -m 644 data/release/selinux/%{modulename}.pp.bz2 %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2

%{__install} -d %{buildroot}%{_datadir}/selinux/devel/include/contrib
%{__install} -m 644 data/release/selinux/%{modulename}.if %{buildroot}%{_datadir}/selinux/devel/include/contrib/

%check
%pytest


%files -f %{pyproject_files}

%{_bindir}/goose-proxy
%doc README.md

# Manpages
%{_mandir}/man5/%{name}-config.5*
%{_mandir}/man7/%{name}.7*

# Needed directories
%dir %attr(0700, root, root) %{_sysconfdir}/xdg/%{name}

# System units
%{_unitdir}/%{name}.service

# Config file
%config(noreplace) %attr(0600, root, root) %{_sysconfdir}/xdg/%{name}/config.toml

# ---------------- Red Hat package

%package    -n goose-redhat
Summary:    %{summary}
	
Requires:   goose
Requires:   %{name} = %{version}-%{release}

%description -n goose-redhat

This package contains Red Hat specific configurations for %{name}, which enable	
the communication with RHEL Lightspeed services.


%files       -n goose-redhat
%{_sysconfdir}/profile.d/goose-init.sh
%{_datadir}/goose-redhat/config.yaml
%{_datadir}/goose-redhat/custom_goose-proxy.json

# ---------------- SELinux package

%package        selinux
Summary:        SELinux policy module for goose-proxy
BuildArch:      noarch

Requires:       selinux-policy >= %{selinux_ver}
Requires:       selinux-policy-%{selinuxtype}
Requires(post): selinux-policy-%{selinuxtype}
Requires(post): selinux-policy-base >= %{selinux_ver}
Requires(post): policycoreutils-python-utils
Requires(postun): policycoreutils-python-utils

%description    selinux
This package installs and sets up the SELinux policy security module for %{modulename}.

%pre            selinux
%selinux_relabel_pre -s %{selinuxtype}

%post           selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2
# Port 8080 may already be assigned to http_cache_port_t; use -m as fallback.
semanage port -a -t goose_proxy_port_t -p tcp 8080 2>/dev/null || \
    semanage port -m -t goose_proxy_port_t -p tcp 8080 2>/dev/null || :

%postun         selinux
if [ $1 -eq 0 ]; then
    semanage port -d -t goose_proxy_port_t -p tcp 8080 2>/dev/null || :
    %selinux_modules_uninstall -s %{selinuxtype} %{modulename}
fi

%posttrans      selinux
%selinux_relabel_post -s %{selinuxtype}

%files          selinux
%attr(0600,root,root) %{_datadir}/selinux/packages/%{selinuxtype}/%{modulename}.pp.bz2
%{_datadir}/selinux/devel/include/contrib/%{modulename}.if
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{modulename}


%changelog
%autochangelog
