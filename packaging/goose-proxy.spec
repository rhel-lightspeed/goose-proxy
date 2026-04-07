Name:           goose-proxy
Version:        0.1.0
Release:        %autorelease
Summary:        A proxy API for RHEL Lightspeed

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

%global _description %{expand:
A lightweight API translation proxy that bridges Goose with backend servers
that speak the Responses API from OpenAI, such as Lightspeed Stack.}

%description %_description


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


%changelog
%autochangelog
