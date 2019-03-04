{
    nixpkgs ? import <nixpkgs> {},
    python_version,
    src ? null,
    name ? null,
    nativeBuildInputs ? [],
    buildInputs ? []
}:

let
    pythonPackages = nixpkgs.${python_version}.pkgs;
    bare_python = pythonPackages.python.withPackages(ps: with ps; [ setuptools packaging ]);

    get_environment = nixpkgs.runCommand "python${python_version}-environment" {} "${bare_python.interpreter} ${./package.py}";

    get_metadata = nix_mode: name: src: buildInputs:
        if name == null || src == null
        then abort "name and src arguments are required"
        else nixpkgs.runCommand "${name}-setup.py-metadata" {
            inherit src buildInputs nativeBuildInputs nix_mode;
        } "${bare_python.interpreter} ${./package.py}";
in {
    environment = get_environment;
    metadata = get_metadata "f" name src buildInputs;
    dependencies = get_metadata "t" name src buildInputs;
}
