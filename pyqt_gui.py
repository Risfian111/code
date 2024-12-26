import sys
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker
import queue
import numpy as np
import sounddevice as sd
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5 import uic
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudio

# Mendapatkan perangkat audio input yang tersedia
input_audio_deviceInfos = QAudioDeviceInfo.availableDevices(QAudio.AudioInput)

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)
        fig.tight_layout()

class PyShine_LIVE_PLOT_APP(QtWidgets.QMainWindow):
    def __init__(self):
        super(PyShine_LIVE_PLOT_APP, self).__init__()
        self.ui = uic.loadUi('main.ui', self)  # Load the UI file
        self.resize(888, 600)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("PyShine.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)
        self.threadpool = QtCore.QThreadPool()

        # Inisialisasi daftar perangkat audio
        self.devices_list = []
        self.devices_info = []  # Menyimpan detail perangkat untuk pencocokan
        for device in input_audio_deviceInfos:
            device_name = device.deviceName()
            self.devices_list.append(device_name)  # Menyimpan hanya nama perangkat
            self.devices_info.append(device)  # Menyimpan objek perangkat

        # Mengisi daftar perangkat di combobox
        self.comboBox.addItems(self.devices_list)
        self.comboBox.currentIndexChanged['QString'].connect(self.update_now)

        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.ui.gridLayout_4.addWidget(self.canvas, 2, 1, 1, 1)
        self.reference_plot = None
        self.q = queue.Queue(maxsize=20)

        self.device = self.devices_info[0]  # Default ke perangkat pertama
        self.window_length = 1000
        self.downsample = 1
        self.channels = [1]
        self.interval = 30

        self.samplerate = 44100
        length = int(self.window_length * self.samplerate / (1000 * self.downsample))
        sd.default.samplerate = self.samplerate

        self.plotdata = np.zeros((length, len(self.channels)))

        self.update_plot()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.interval)  # dalam milidetik
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

        self.lineEdit.textChanged['QString'].connect(self.update_window_length)
        self.lineEdit_2.textChanged['QString'].connect(self.update_sample_rate)
        self.lineEdit_3.textChanged['QString'].connect(self.update_down_sample)
        self.lineEdit_4.textChanged['QString'].connect(self.update_interval)
        self.pushButton.clicked.connect(self.start_worker)

    def getAudio(self):
        """Mendapatkan stream audio dari perangkat yang dipilih."""
        try:
            def audio_callback(indata, frames, time, status):
                self.q.put(indata[::self.downsample, [0]])

            # Mencocokkan perangkat yang dipilih dengan perangkat di sounddevice
            device_index = self.devices_info.index(self.device)
            stream = sd.InputStream(device=device_index, channels=max(self.channels), samplerate=self.samplerate, callback=audio_callback)
            with stream:
                input()  # Blokir sampai pengguna menginterupsi
        except Exception as e:
            print("ERROR: ", e)

    def start_worker(self):
        """Memulai worker untuk mengambil dan memproses audio."""
        worker = Worker(self.start_stream)
        self.threadpool.start(worker)

    def start_stream(self):
        """Memulai streaming dan menonaktifkan UI selama proses berjalan."""
        self.lineEdit.setEnabled(False)
        self.lineEdit_2.setEnabled(False)
        self.lineEdit_3.setEnabled(False)
        self.lineEdit_4.setEnabled(False)
        self.comboBox.setEnabled(False)
        self.pushButton.setEnabled(False)
        self.getAudio()

    def update_now(self, value):
        """Memperbarui perangkat audio yang dipilih."""
        selected_device_name = value  # Nama perangkat dipilih
        print(f"Selected device: {selected_device_name}")
        selected_device = None
        for device in self.devices_info:
            if device.deviceName() == selected_device_name:
                selected_device = device
                break
        if selected_device:
            self.device = selected_device
            print(f"Device set to: {self.device.deviceName()}")

    def update_window_length(self, value):
        """Memperbarui panjang jendela berdasarkan input pengguna."""
        self.window_length = int(value)
        length = int(self.window_length * self.samplerate / (1000 * self.downsample))
        self.plotdata = np.zeros((length, len(self.channels)))
        self.update_plot()

    def update_sample_rate(self, value):
        """Memperbarui sample rate berdasarkan input pengguna."""
        self.samplerate = int(value)
        sd.default.samplerate = self.samplerate
        length = int(self.window_length * self.samplerate / (1000 * self.downsample))
        self.plotdata = np.zeros((length, len(self.channels)))
        self.update_plot()

    def update_down_sample(self, value):
        """Memperbarui tingkat downsample."""
        self.downsample = int(value)
        length = int(self.window_length * self.samplerate / (1000 * self.downsample))
        self.plotdata = np.zeros((length, len(self.channels)))
        self.update_plot()

    def update_interval(self, value):
        """Memperbarui interval pembaruan untuk plot."""
        self.interval = int(value)
        self.timer.setInterval(self.interval)  # dalam milidetik
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def update_plot(self):
        """Memperbarui plot dengan data audio baru."""
        try:
            data = [0]
            while True:
                try:
                    data = self.q.get_nowait()
                except queue.Empty:
                    break
                shift = len(data)
                self.plotdata = np.roll(self.plotdata, -shift, axis=0)
                self.plotdata[-shift:, :] = data
                self.ydata = self.plotdata[:]
                self.canvas.axes.set_facecolor((0, 0, 0))

                if self.reference_plot is None:
                    plot_refs = self.canvas.axes.plot(self.ydata, color=(0, 1, 0.29))
                    self.reference_plot = plot_refs[0]
                else:
                    self.reference_plot.set_ydata(self.ydata)

            self.canvas.axes.yaxis.grid(True, linestyle='--')
            start, end = self.canvas.axes.get_ylim()
            self.canvas.axes.yaxis.set_ticks(np.arange(start, end, 0.1))
            self.canvas.axes.yaxis.set_major_formatter(ticker.FormatStrFormatter('%0.1f'))
            self.canvas.axes.set_ylim(ymin=-0.5, ymax=0.5)
            self.canvas.draw()
        except Exception as e:
            print("Error in updating plot:", e)

# Worker class to run audio stream in a separate thread
class Worker(QtCore.QRunnable):
    def __init__(self, function, *args, **kwargs):
        super(Worker, self).__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        self.function(*self.args, **self.kwargs)

# Main application code
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = PyShine_LIVE_PLOT_APP()
    mainWindow.show()
    sys.exit(app.exec_())
