# 3D Printer Connection Hub

A powerful, centralized gateway for managing and merging 3D printers from different manufacturers (Bambu Lab, Klipper/Moonraker, Elegoo) into a single, unified dashboard. Designed to run headless on a dedicated machine (like a Raspberry Pi or Mini PC) but accessible from any device via a responsive web interface.

![Dashboard Preview](https://via.placeholder.com/800x400?text=Dashboard+Preview) <!-- Replace with actual screenshot later -->

## Key Features

*   **Unified Dashboard**: Monitor multiple printers in real-time on a single screen. No more tab switching between different printer IPs.
*   **Multi-Brand Support**: Seamlessly integrate printers from different ecosystems:
    *   **Bambu Lab**: Full status monitoring via secure MQTT.
    *   **Klipper / Moonraker**: Standard integration for Vorons, Creality K1/max (rooted), and other Klipper-based machines.
    *   **Elegoo (Saturn Series)**: Direct UDP communication for resin printers like the Saturn 3 Ultra.
*   **System Monitor**: Built-in resource tracking for the host machine (CPU, RAM, Disk, Network I/O) to ensure smooth operation.
*   **Responsive Design**: Mobile-friendly interface that works great on desktops, tablets, and smartphones.
*   **Secure Token Storage**: Safely manages integration tokens for external cloud connectivity.
*   **Extensible Driver System**: Modular Python architecture makes adding new printer types easy.

## Supported Hardware

The application currently includes drivers for:
*   **Bambu Lab**: X1C, P1S, A1, A1 Mini (requires Access Code & Serial).
*   **Klipper**: Any printer running Moonraker API (e.g., Voron, RatRig, Creality K1/Max).
*   **Elegoo**: Tested with Saturn 3 Ultra (Reference Implementation for Chitu Systems).

## Installation

### Prerequisites
*   Python 3.8 or higher
*   `pip` package manager

### Steps

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
    cd 3d_printer_connection_hub
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Application**
    ```bash
    python app.py
    ```

4.  **Access the Dashboard**
    Open your web browser and navigate to:
    `http://localhost:5000` or `http://<your-machine-ip>:5000`

## Configuration

### Adding a Printer
1.  Navigate to the **Printers** tab on the sidebar.
2.  Click the **Add Printer** button in the top right.
3.  Select your printer type (Bambu, Moonraker, or Elegoo).
4.  Enter the required details (IP Address, Serial Number, Access Code, etc.).
5.  Click **Add**. The printer will appear instantly on the dashboard.

### System Monitoring
Navigate to the **System Monitor** tab to view real-time stats of the host machine, including specific resource usage of the Python Hub application itself.

## Architecture

The project is built with:
*   **Backend**: Python (Flask) for the web server and API.
*   **Frontend**: HTML5, CSS3 (Custom responsive design), JavaScript (Fetch API, Chart.js).
*   **Protocols**: MQTT (Bambu), HTTP REST (Moonraker), UDP (Elegoo).

## Contributing

Contributions are welcome! If you'd like to add support for a new printer brand:
1.  Fork the repository.
2.  Create a new driver class inheriting from `BasePrinter` in `printer_drivers.py`.
3.  Update the `create_printer` factory function.
4.  Submit a Pull Request.

## License

MIT License - feel free to use and modify for your own setups.
