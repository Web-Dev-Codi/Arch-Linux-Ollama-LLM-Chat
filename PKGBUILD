pkgname=ollamaterm
pkgver=0.5.0
pkgrel=1
pkgdesc='Chat TUI for Ollama local LLMs'
arch=('any')
url='https://github.com/brian/Arch-Linux-Ollama-LLM-Chat'
license=('MIT')
depends=('python' 'python-textual' 'python-ollama' 'ollama')
makedepends=('python-setuptools' 'python-build' 'python-installer' 'python-wheel')
source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  cd "$pkgname-$pkgver"
  python -m build --wheel --no-isolation
}

package() {
  cd "$pkgname-$pkgver"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 config.example.toml "$pkgdir/usr/share/doc/$pkgname/config.example.toml"
}
