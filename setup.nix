let
	setup = args@{
		nixpkgs ? import <nixpkgs> {},

		python, # python27, python36 etc

		# project path, usually ./.
		src,

		application ? false,

		checkInputs ? [],

		buildInputs ? [],

		propagatedBuildInputs ? [],

		doCheck ? false,

		override_packages ? null
	}:

	with builtins;

	let
		pkgs = import nixpkgs {};
		pythonPackages = nixpkgs.${python}.pkgs;
		buildPython = if application then pythonPackages.buildPythonApplication else pythonPackages.buildPythonPackage;

		# Import requirements
		requirements = let
			requirements_path = src + "/requirements.nix";
		in if pathExists requirements_path then import requirements_path {
			inherit setup args;
			inherit (nixpkgs) fetchurl;
			inherit (pythonPackages) buildPythonPackage;
		} else self: {};

		# Requirement overrides
		requirements_override = let
			requirements_path = src + "/requirements_override.nix";
		in if pathExists requirements_path then import requirements_path {
			inherit nixpkgs;
		} else self: super: {};

		packages = if isNull override_packages then
			nixpkgs.lib.fix (nixpkgs.lib.extends requirements_override requirements)
		else
			override_packages;

		# Obtain metadata for the current package
		package_metadata = nixpkgs.lib.importJSON((import ./pynixreq/nix/package.nix {
			python_version = python;
			name = (baseNameOf (if isAttrs src then src.name else src));
#			buildInputs = [packages.setuptools_scm nixpkgs.git]; # TODO: automatically detect it
			nativeBuildInputs = [nixpkgs.git];
			buildInputs = [pythonPackages.setuptools_scm]; # TODO: automatically detect it
			inherit nixpkgs src;
		}).dependencies);

#		packages = if isNull override_packages then
#			(nixpkgs.lib.fix
#			(nixpkgs.lib.extends overrides
#			(nixpkgs.lib.extends req_derivations
#			pythonPackages.__unfix__))) else override_packages;

		filter_python_files = with nixpkgs.lib; src: cleanSourceWith {
			filter = (name: type: let baseName = baseNameOf (toString name); parent = dirOf name; srcDir = toString src; in ! (
				(type == "regular" && hasSuffix ".pyc" baseName) ||
				(type == "directory" && baseName == "__pycache__") ||
				(type == "directory" && parent == srcDir && hasSuffix ".egg-info" baseName) ||
				(type == "directory" && parent == srcDir && baseName == ".DS_Store") ||
				(type == "directory" && parent == srcDir && baseName == ".eggs") ||
				(type == "directory" && parent == srcDir && baseName == ".idea") ||
				(type == "directory" && parent == srcDir && baseName == ".mypy_cache") ||
				(type == "directory" && parent == srcDir && baseName == "venv") ||
				(type == "directory" && parent == srcDir && toLower baseName == "build") ||
				(type == "directory" && parent == srcDir && toLower baseName == "dist")));
			inherit src;
		};
		clean_python_source = src: nixpkgs.lib.cleanSource (filter_python_files src);

	in buildPython {
			pname = package_metadata.metadata.name;
			version = package_metadata.metadata.version;
			src = if nixpkgs.lib.isStorePath (toPath src) then src else clean_python_source src;

			checkInputs = checkInputs ++ nixpkgs.lib.attrVals package_metadata.requirements.test packages;
			buildInputs = buildInputs ++ nixpkgs.lib.attrVals package_metadata.requirements.setup packages;
			propagatedBuildInputs = propagatedBuildInputs ++ nixpkgs.lib.attrVals package_metadata.requirements.install packages;

			passthru = {
				python = nixpkgs.${python};
			};

			inherit doCheck;
#			inherit postInstall;
			SETUPTOOLS_SCM_PRETEND_VERSION = package_metadata.metadata.version;
	};
in setup
