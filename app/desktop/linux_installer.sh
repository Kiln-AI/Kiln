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
    local missing_tools=""
    
    # Check for download tool
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        missing_tools="curl or wget"
    fi
    
    # Check for unzip
    if ! command -v unzip >/dev/null 2>&1; then
        if [ -n "$missing_tools" ]; then
            missing_tools="$missing_tools, unzip"
        else
            missing_tools="unzip"
        fi
    fi
    
    if [ -n "$missing_tools" ]; then
        print_error "Missing required tools: $missing_tools"
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
    print_info "Download URL: $url"
    print_info "Target file: $PWD/$output"
    
    # Check if we can write to current directory
    if ! touch "$output" 2>/dev/null; then
        print_error "Cannot write to current directory: $PWD"
        print_error "Please ensure you have write permissions or try running with appropriate privileges."
        exit 1
    fi
    rm -f "$output"  # Remove the test file
    
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fsSL -o "$output" "$url"; then
            print_error "Failed to download Kiln. Please check your internet connection."
            print_error "You can try downloading manually from: $url"
            exit 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -q -O "$output" "$url"; then
            print_error "Failed to download Kiln. Please check your internet connection."
            print_error "You can try downloading manually from: $url"
            exit 1
        fi
    fi
    
    # Verify the file was created and has content
    if [ ! -f "$output" ] || [ ! -s "$output" ]; then
        print_error "Download completed but file is missing or empty: $output"
        exit 1
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

# Download and install Kiln icon
install_icon() {
    local temp_dir="$1"
    local icon_url="https://github.com/Kiln-AI/Kiln/raw/main/app/desktop/linux_icon.png"
    
    # Create icon directory
    if ! mkdir -p "$icon_dir" 2>/dev/null; then
        return 1
    fi
    
    # Download icon (silently, don't fail installation if this fails)
    local downloaded=false
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$temp_dir/kiln-icon.png" "$icon_url" 2>/dev/null && downloaded=true
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$temp_dir/kiln-icon.png" "$icon_url" 2>/dev/null && downloaded=true
    fi
    
    # Install icon if download was successful
    if [ "$downloaded" = true ] && command -v xdg-icon-resource >/dev/null 2>&1; then
        xdg-icon-resource install --mode user --context apps --size 256 "$temp_dir/kiln-icon.png" kiln-kilnicon >/dev/null 2>&1 && return 0
    fi
    
    return 1
}

# Create desktop entry for GUI access
create_desktop_entry() {
    local temp_dir="$1"
    local desktop_dir="$HOME/.local/share/applications"
    local desktop_file="$desktop_dir/kiln.desktop"
    local icon_name="application-x-executable"  # fallback icon
    
    # Only create desktop entry if we can write to the directory
    if ! mkdir -p "$desktop_dir" 2>/dev/null; then
        print_warning "Could not create applications directory. Skipping desktop entry."
        return 0
    fi
    
    # Try to install the Kiln icon, Optional
    if install_icon "$temp_dir"; then
        icon_name="kiln-kilnicon"  # Use our custom icon
        print_info "Downloaded Kiln icon"
    fi
    
    # Create the desktop entry file
    if cat > "$desktop_file" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Kiln
Comment=Kiln AI Development Environment
Exec=$KILN_PATH
Icon=$icon_name
Terminal=false
Categories=Development;IDE;
StartupWMClass=Kiln
EOF
    then
        chmod +x "$desktop_file" 2>/dev/null || true
        print_info "Created desktop entry for Kiln"
        return 0
    else
        print_warning "Could not create desktop entry. Kiln installed but may not appear in application menu."
        return 0
    fi
}

# Install or upgrade Kiln
install_kiln() {
    # Make a temporary directory. In home as some systems have permission issues with /tmp. We'll clean it up later.
    TEMP_DIR=$(mktemp -d "$HOME/kiln_installer_tmp.XXXXXX")
    
    # Remove any existing directory with this name and create fresh
    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR"
    
    if [ ! -d "$TEMP_DIR" ] || [ ! -w "$TEMP_DIR" ]; then
        print_error "Failed to create download directory: $TEMP_DIR"
        exit 1
    fi
    
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
    
    # Create desktop entry (non-fatal if it fails)
    create_desktop_entry "$TEMP_DIR"
    
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
    if [ -f "$HOME/.local/share/applications/kiln.desktop" ]; then
        echo "  • Desktop entry created for GUI access"
    else
        echo "  • Desktop entry creation skipped (non-fatal)"
    fi
    
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
    exit "$exit_code"
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
