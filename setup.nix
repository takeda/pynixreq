let
	setup = args@{
		nixpkgs ? import <nixpkgs>,

		python, # python27, python36 etc

		# project path, usually ./.
		src,

		buildInputs ? [],

		propagatedBuildInputs ? [],

		doCheck ? false,

		override_packages ? null
	}:

	with builtins;

	let
		pkgs = nixpkgs {};
		pythonPackages = pkgs.${python}.pkgs;

		# Import requirements
		requirements = let
			requirements_path = src + "/requirements.nix";
		in if pathExists requirements_path then import requirements_path {
			inherit setup args;
			inherit (pkgs) fetchurl;
			inherit (pythonPackages) buildPythonPackage;
		} else self: {};

		# Requirement overrides
		requirements_override = let
			requirements_path = src + "/requirements_override.nix";
		in if pathExists requirements_path then import requirements_path {
			inherit pkgs;
		} else self: super: {};

		packages = if isNull override_packages then
			pkgs.lib.fix (pkgs.lib.extends requirements_override requirements)
		else
			override_packages;

		# Obtain metadata for the current package
		package_metadata = pkgs.lib.importJSON((import ./pynixreq/nix/package.nix {
			python_version = python;
			name = (baseNameOf (if isAttrs src then src.name else src));
#			buildInputs = [packages.setuptools_scm pkgs.git]; # TODO: automatically detect it
			nativeBuildInputs = [pkgs.git];
			buildInputs = [pythonPackages.setuptools_scm]; # TODO: automatically detect it
			inherit pkgs src;
		}).dependencies);

#		packages = if isNull override_packages then
#			(pkgs.lib.fix
#			(pkgs.lib.extends overrides
#			(pkgs.lib.extends req_derivations
#			pythonPackages.__unfix__))) else override_packages;

		filter_python_files = with pkgs.lib; src: cleanSourceWith {
			filter = (name: type: let baseName = baseNameOf (toString name); parent = dirOf name; srcDir = toString src; in ! (
				(type == "regular" && hasSuffix ".pyc" baseName) ||
				(type == "directory" && baseName == "__pycache__") ||
				(type == "directory" && parent == srcDir && hasSuffix ".egg-info" baseName) ||
				(type == "directory" && parent == srcDir && baseName == ".eggs") ||
				(type == "directory" && parent == srcDir && baseName == ".idea") ||
				(type == "directory" && parent == srcDir && toLower baseName == "build") ||
				(type == "directory" && parent == srcDir && toLower baseName == "dist")));
			inherit src;
		};
		clean_python_source = src: pkgs.lib.cleanSource (filter_python_files src);

	in pythonPackages.buildPythonPackage {
			pname = package_metadata.metadata.name;
			version = package_metadata.metadata.version;
			src = if pkgs.lib.isStorePath (toPath src) then src else clean_python_source src;

#			checkInputs = checkInputs ++ pkgs.lib.attrVals package_metadata.requirement_names.test packages;
#			buildInputs = buildInputs ++ pkgs.lib.attrVals package_metadata.requirement_names.setup packages;
			propagatedBuildInputs = propagatedBuildInputs ++ pkgs.lib.attrVals package_metadata.requirements.install packages;

			inherit doCheck;
#			inherit postInstall;
			SETUPTOOLS_SCM_PRETEND_VERSION = package_metadata.metadata.version;
	};
in setup
