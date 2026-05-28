# Linux and Filesystem Simulator 🐧

An interactive web-based application designed to bridge the gap between theoretical Operating System concepts and practical understanding. This simulator visually demonstrates how a real Linux file system operates internally.

By interacting with the simulator, users can clearly see how files are stored in disk blocks, how directories are structured via inodes, and how terminal commands affect the system in real-time.

## Features

- **Disk & Memory Visualization**: A dynamic grid displays real-time disk block allocation (64 blocks of 512 bytes), indicating free, used, and system-reserved blocks.
- **Inode Management**: Every file and directory is tracked using an inode structure, which handles metadata like file size, permissions, and creation timestamps.
- **Allocation Strategies**: Implements the **First Fit** algorithm and allows users to allocate files using three distinct strategies:
  - Contiguous Allocation
  - Linked Allocation
  - Indexed Allocation
- **Linux Terminal Interface**: A built-in terminal allowing users to run standard Linux commands (`ls`, `cd`, `mkdir`, `rm`, `chmod`, `stat`, `pwd`, `cp`, `mv`).
- **Live Access Logs**: Every read and write operation is logged step-by-step to provide deep insight into internal data processing.

## Tech Stack 💻

- **Backend**: Python (Flask)
- **Frontend**: HTML5, CSS3, JavaScript
- **Architecture**: Client-Server API

## Installation & Setup 🚀

To run this simulator locally on your machine, follow these steps:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ronakkatakiya123/Linux-and-Filesystem-Simulator.git
   cd Linux-and-Filesystem-Simulator
   ```

2. **Install the required dependencies:**
   Make sure you have Python installed, then install Flask:
   ```bash
   pip install flask
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Access the Simulator:**
   Open your web browser and navigate to:
   ```text
   http://localhost:5000
   ```

## Author ✍️

**Ronak Katakiya**
- GitHub: [@ronakkatakiya123](https://github.com/ronakkatakiya123)

---
*This project was developed as part of an Operating Systems academic assignment to convert theoretical concepts into practical understanding.*
