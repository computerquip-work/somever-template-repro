Upstream WiX 7.0.1 uses SomeVer to generate five version files from different
templates. SomeVer 0.1.1 can leave them stale after a Git version change;
upgrading to 0.1.2 writes the last template's XML into every file instead.

These are direct Bash commands using Git, .NET SDK 10, and standard Unix
tools. Run them from a directory outside any checkout that pins an older
.NET SDK. This reproduces WiX's version bootstrap, not a full WiX build.

### SomeVer 0.1.1: stale versions

```sh
mkdir somever-wix-repro
cd somever-wix-repro
export NUGET_PACKAGES="$PWD/build/packages"
git clone --depth 1 --branch v7.0.1 https://github.com/wixtoolset/wix.git wix
git -C wix rev-parse HEAD
dotnet build wix/src/internal/SetBuildNumber/SomeVerInit.verproj
grep '"WixToolset.Sdk"' wix/global.json
```

The upstream revision is `642f1a0f7c857ffa4fc9fa3f9d1433aab895dd29`.
The generated SDK version is `7.0.1`. Now add a local tag without touching
any templates, and rebuild:

```sh
git -C wix tag v7.0.2
dotnet build wix/src/internal/SetBuildNumber/SomeVerInit.verproj
grep '"WixToolset.Sdk"' wix/global.json
```

The version should become `7.0.2`, but stays `7.0.1`: the target skips
generation because its template files haven't changed.

### SomeVer 0.1.2: wrong template contents

Change only the SDK version in WiX's bootstrap project:

```sh
sed -i.bak 's|SomeVer/0.1.1|SomeVer/0.1.2|' \
    wix/src/internal/SetBuildNumber/SomeVerInit.verproj
dotnet build wix/src/internal/SetBuildNumber/SomeVerInit.verproj
head -n 4 wix/global.json wix/Directory.Packages.props \
    wix/build/SomeVerInfo.cs wix/build/SomeVerInfo.rc wix/build/SomeVerInfo.props
```

Generation succeeds, but all five files contain XML from `SomeVerInfo.props.pp`.
`global.json` should contain JSON, `.cs` should contain C#, and `.rc` should
contain Windows resource definitions. The next .NET invocation inside WiX
fails because its `global.json` is now XML:

```sh
(cd wix && dotnet --version)
```

### Try the one-line fix

Open `build/packages/somever/0.1.2/build/SomeVer.targets` and add `Outputs`
to this target. This edits only the isolated package cache created above:

```diff
   <Target Name="SomeVerApplyVersionTemplates"
+          Outputs="%(VersionTemplate.OutputPath)"
           Condition="'$(DesignTimeBuild)' != 'true' AND '$(SomeVerSkip)' != 'true' AND '@(VersionTemplate)' != ''">
```

This batches the whole target by output path, keeping each template's read,
substitution, and write together. Leave `Inputs` absent so Git changes don't
get skipped. See Microsoft's
[batching and property mutation explanation](https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-batching#item-and-property-mutations).

Use a fresh upstream checkout because the first one's corrupted `global.json`
blocks SDK resolution. Keep the broken files around to compare:

```sh
git clone --depth 1 --branch v7.0.1 https://github.com/wixtoolset/wix.git wix-fixed
dotnet build wix-fixed/src/internal/SetBuildNumber/SomeVerInit.verproj
git -C wix-fixed tag v7.0.2
sed -i.bak 's|SomeVer/0.1.1|SomeVer/0.1.2|' \
    wix-fixed/src/internal/SetBuildNumber/SomeVerInit.verproj
dotnet build wix-fixed/src/internal/SetBuildNumber/SomeVerInit.verproj
head -n 4 wix-fixed/global.json wix-fixed/Directory.Packages.props \
    wix-fixed/build/SomeVerInfo.cs wix-fixed/build/SomeVerInfo.rc \
    wix-fixed/build/SomeVerInfo.props
grep -n '7\.0\.2' wix-fixed/global.json wix-fixed/Directory.Packages.props \
    wix-fixed/build/SomeVerInfo.cs wix-fixed/build/SomeVerInfo.rc \
    wix-fixed/build/SomeVerInfo.props
```

Each file now has its own template's contents and the updated `7.0.2` version.

Run the bootstrap from the parent directory as shown: WiX generates a .NET 9
SDK pin, while SomeVer 0.1.2 requires .NET 10. The fix keeps WiX's templates
unchanged.
