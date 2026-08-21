project(
  'dedisc',
  'c',
  version : '0.1.0',
  license : 'MIT',
  default_options : [
    'prefix=/usr',
  ]
)

py = import('python').find_installation(pure: true)

conf = configuration_data()
conf.set('APP_ID', 'pl.septicwolf818.Dedisc')

configured_desktop = configure_file(
  input: 'data/dedisc.desktop.in',
  output: 'dedisc.desktop',
  configuration: conf,
)

i18n = import('i18n')
i18n.merge_file(
  input: configured_desktop,
  output: 'pl.septicwolf818.Dedisc.desktop',
  type: 'desktop',
  po_dir: join_paths(meson.project_source_root(), 'po'),
  install: true,
  install_dir: join_paths(get_option('datadir'), 'applications')
)

install_data(
  'data/pl.septicwolf818.Dedisc.svg',
  install_dir : join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps')
)

subdir('src')
subdir('po')