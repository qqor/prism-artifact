OSS_FUZZ_DEFAULT_CFLAGS = "-O1   -fno-omit-frame-pointer   -gline-tables-only   -Wno-error=enum-constexpr-conversion   -Wno-error=incompatible-function-pointer-types   -Wno-error=int-conversion   -Wno-error=deprecated-declarations   -Wno-error=implicit-function-declaration   -Wno-error=implicit-int   -Wno-error=vla-cxx-extension   -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"

OSS_FUZZ_DEFAULT_CXXFLAGS_EXTRA = "-stdlib=c++"
OSS_FUZZ_DEFAULT_CXXFLAGS = (
    f"{OSS_FUZZ_DEFAULT_CFLAGS} {OSS_FUZZ_DEFAULT_CXXFLAGS_EXTRA}"
)
