# dev shell: extension build (node) + glasslab test suite (python, ffmpeg for video wallpapers). Zen itself = Flatpak.
{ pkgs ? import <nixpkgs> { } }:
pkgs.mkShell {
  packages = with pkgs; [
    nodejs_22
    (python3.withPackages (p: [ p.websockets p.pillow p.numpy ]))
    ffmpeg
  ];
}
