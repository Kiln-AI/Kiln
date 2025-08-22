#!/bin/bash

# Kiln Linux installer script
# Downloads and installs Kiln for Linux systems

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_error() {
    echo -e "${RED}Error: $1${NC}" >&2
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_info() {
    echo -e "${BLUE}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

# Check if we're on a supported platform
check_platform() {
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    
    if [ "$OS" != "linux" ]; then
        print_error "This installer is only for Linux systems."
        echo "For other platforms, please download the installer from:"
        echo "https://kiln.tech/download"
        exit 1
    fi
}

# Detect architecture
detect_architecture() {
    ARCH=$(uname -m)
    
    case $ARCH in
        x86_64)
            RELEASE_NAME="Kiln.Linux.x64.zip"
            ARCH_DISPLAY="x64"
            ;;
        aarch64|arm64)
            RELEASE_NAME="Kiln.Linux.ARM.zip"
            ARCH_DISPLAY="ARM64"
            ;;
        *)
            print_error "Unsupported architecture: $ARCH"
            echo "Kiln is available for x64 and ARM64 Linux systems."
            echo "Please visit https://kiln.tech/download for more options."
            exit 1
            ;;
    esac
    
    DOWNLOAD_URL="https://github.com/Kiln-AI/Kiln/releases/latest/download/${RELEASE_NAME}"
}

# Check for required tools
check_dependencies() {
    local missing_tools=()
    
    # Check for download tool
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        missing_tools+=("curl or wget")
    fi
    
    # Check for unzip
    if ! command -v unzip >/dev/null 2>&1; then
        missing_tools+=("unzip")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        echo "Please install the missing tools and try again."
        echo "On Ubuntu/Debian: sudo apt update && sudo apt install curl unzip"
        echo "On CentOS/RHEL: sudo yum install curl unzip"
        echo "On Fedora: sudo dnf install curl unzip"
        exit 1
    fi
}

# Download file using available tool
download_file() {
    local url="$1"
    local output="$2"
    
    print_info "Downloading Kiln for Linux ($ARCH_DISPLAY)..."
    
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fsSL -o "$output" "$url"; then
            print_error "Failed to download Kiln. Please check your internet connection."
            exit 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -q -O "$output" "$url"; then
            print_error "Failed to download Kiln. Please check your internet connection."
            exit 1
        fi
    fi
}

# Determine installation directory
get_install_dir() {
    # Try /usr/local/bin first (requires sudo on most systems)
    if [ -w "/usr/local/bin" ]; then
        INSTALL_DIR="/usr/local/bin"
        INSTALL_TYPE="system"
    else
        # Fallback to ~/.local/bin (user installation)
        INSTALL_DIR="$HOME/.local/bin"
        INSTALL_TYPE="user"
        mkdir -p "$INSTALL_DIR"
    fi
    
    KILN_PATH="$INSTALL_DIR/kiln"
}

# Create desktop entry for GUI access
create_desktop_entry() {
    local desktop_dir="$HOME/.local/share/applications"
    local desktop_file="$desktop_dir/kiln.desktop"
    
    mkdir -p "$desktop_dir"
    
    cat > "$desktop_file" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Kiln
Comment=Kiln AI Development Environment
Exec=$KILN_PATH
Icon=kiln
Terminal=false
Categories=Development;IDE;
StartupWMClass=Kiln
EOF
    
    chmod +x "$desktop_file"
    print_info "Created desktop entry for Kiln"
}

# Install or upgrade Kiln
install_kiln() {
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Download the zip file
    download_file "$DOWNLOAD_URL" "kiln.zip"
    
    # Extract the zip file
    print_info "Extracting Kiln..."
    if ! unzip -q kiln.zip; then
        print_error "Failed to extract downloaded file. The download may be corrupted."
        cleanup_and_exit 1
    fi
    
    # Check if the Kiln executable exists
    if [ ! -f "Kiln" ]; then
        print_error "Expected 'Kiln' executable not found in the downloaded archive."
        cleanup_and_exit 1
    fi
    
    # Check if this is an upgrade
    if [ -f "$KILN_PATH" ]; then
        print_info "Existing Kiln installation found. Upgrading..."
        UPGRADE=true
    else
        print_info "Installing Kiln..."
        UPGRADE=false
    fi
    
    # Install the binary
    cp "Kiln" "$KILN_PATH"
    chmod +x "$KILN_PATH"
    
    # Create desktop entry
    create_desktop_entry
    
    # Clean up temporary files
    cd /
    rm -rf "$TEMP_DIR"
    
    # Success message
    if [ "$UPGRADE" = true ]; then
        print_success "Kiln upgraded successfully!"
    else
        print_success "Kiln installed successfully!"
    fi
    
    echo ""
    print_info "Installation details:"
    echo "  • Executable: $KILN_PATH"
    echo "  • Desktop entry created for GUI access"
    
    if [ "$INSTALL_TYPE" = "user" ]; then
        echo ""
        print_warning "Note: Kiln was installed to your user directory."
        echo "If 'kiln' command is not found, add this to your shell profile:"
        echo "  export PATH=\$PATH:\$HOME/.local/bin"
        echo "Then restart your terminal or run: source ~/.bashrc"
    fi
    
    echo ""
    echo "You can now:"
    echo "  • Run 'kiln' from the command line"
    echo "  • Launch Kiln from your applications menu"
    echo "  • Or run directly: $KILN_PATH"
}

# Cleanup function
cleanup_and_exit() {
    local exit_code=${1:-0}
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
    exit $exit_code
}

# Trap to ensure cleanup on script exit
trap 'cleanup_and_exit $?' EXIT

# Main execution
main() {
    echo "Kiln Linux Installer"
    echo "===================="
    echo ""
    
    check_platform
    detect_architecture
    check_dependencies
    get_install_dir
    install_kiln
}

# Run main function
main "$@"
