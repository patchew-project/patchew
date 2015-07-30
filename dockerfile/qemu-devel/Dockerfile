FROM fedora:22
RUN dnf install ccache git mingw{32,64}-{pixman,glib2,gmp,SDL,pkg-config} \
    glib2-devel pixman-devel zlib-devel SDL-devel gcc make perl which bc findutils
ADD build.sh
