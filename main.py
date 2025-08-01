import sys
import cv2
import torch
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import qtawesome as qta
import time

from Ui_components import NavBarWidget, HudOverlay, UIWidgetManager

class TrackingSystem(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Detection and Tracking Drone UI")
        screen_rect = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_rect)
        self.setStyleSheet("background-color: #262423")

        self.selected_target_id = 1

        # Load YOLOv5
        # model_path = "model/yolov5s.pt"  
        # self.yolo_model = torch.hub.load('ultralytics/yolov5', 'custom', path=model_path, force_reload=False)

        # open video 
        self.cap = cv2.VideoCapture("video/drone-flying.mp4")

        # Open CSI camera via GStreamer
        # self.cap = cv2.VideoCapture(gstreamer_pipeline(), cv2.CAP_GSTREAMER)
        # if not self.cap.isOpened():
        #     print(" No Open Camera ")
        #     sys.exit()




        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        # Count FPS variables
        self.fps_counter = 0 
        self.fps_start_time = time.time()
        self.current_fps = 0

        # Tracking variables
        self.detected_drone = []
        self.compass_bearing = 0

        # zoom object power
        self.zoom_level = 0.5  # center

        self.init_ui()
        self.video_paused = False

    def init_ui(self):
        # Full Screen video
        self.video_label = QLabel(self)
        self.video_label.setGeometry(0, 0, 1920, 1080)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)

        # HUD overlay
        self.hud_overlay = HudOverlay(self.video_label)
        self.hud_overlay.resize(self.video_label.size())
        self.hud_overlay.show()

        # NavBarWidget 
        self.nav_bar_widget = NavBarWidget(self.video_label)
        self.nav_bar_widget.setGeometry(0, 0, self.video_label.width(), 60)
        self.nav_bar_widget.setStyleSheet("background-color: transparent;")

        # Initialize UI Widget Manager
        self.ui_manager = UIWidgetManager(self.video_label)

        # Icons
        self.icon_eye_open = qta.icon('fa5s.eye', color='white')
        self.icon_eye_closed = qta.icon('fa5s.eye-slash', color='white')


        # Set up widget connections
        self.setup_widget_connections()

        self.zoom_visible = True
        self.ui_manager.place_toggle_button(True, self.nav_bar_widget.height())

        # update play/pause position
        self.ui_manager.update_widget_positions(self.video_label.width(), self.video_label.height(), self.nav_bar_widget.height())


    # set widget connection
    def setup_widget_connections(self):
        # Toggle zoom button
        toggle_button = self.ui_manager.get_widget('toggle_zoom_button')
        toggle_button.clicked.connect(self.toggle_zoom_view)
        
        # Play/Pause button
        play_pause_button = self.ui_manager.get_widget('play_pause_button')
        play_pause_button.clicked.connect(self.toggle_video_playback)
        
        self.update_play_pause_button_position()

    # update play/pause
    def update_play_pause_button_position(self):
        self.ui_manager.update_widget_positions(
            self.video_label.width(), 
            self.video_label.height(), 
            self.nav_bar_widget.height()
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_play_pause_button_position()

        self.video_label.setGeometry(0, 0, self.width(), self.height())
        self.nav_bar_widget.setGeometry(0, 0, self.video_label.width(), 60) 
        self.ui_manager.update_widget_positions(self.width(), self.height(), nav_bar_height=80)


        # Update UI widgets positions
        self.ui_manager.update_widget_positions(
            self.video_label.width(), 
            self.video_label.height(), 
            self.nav_bar_widget.height()
        )
        
        self.ui_manager.place_toggle_button(self.zoom_visible, self.nav_bar_widget.height())
        
        self.hud_overlay.resize(self.video_label.size())
        self.hud_overlay.update()

    def toggle_video_playback(self):
        if self.video_paused:
            self.video_paused = False
            self.timer.start()                   
        else:
            self.video_paused = True
            self.timer.stop()
        
        # Update buttons via UI manager
        self.ui_manager.update_play_pause_button(self.video_paused)

    def toggle_zoom_view(self):
        # Toggle zoom view display via UI manager
        self.zoom_visible = self.ui_manager.toggle_zoom_view_visibility()
        
        # update icon button
        toggle_button = self.ui_manager.get_widget('toggle_zoom_button')
        if self.zoom_visible:
            toggle_button.setIcon(self.icon_eye_open)
        else:
            toggle_button.setIcon(self.icon_eye_closed)
            
        self.ui_manager.place_toggle_button(self.zoom_visible, self.nav_bar_widget.height())

    def update_frame(self):
        if self.video_paused:
            return

        ret, frame_bgr = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return

        # FPS counter
        self.fps_counter += 1
        elapsed = time.time() - self.fps_start_time
        if elapsed >= 1.0:
            self.current_fps = self.fps_counter
            self.fps_counter = 0
            self.fps_start_time = time.time()

        frame_for_zoom = frame_bgr.copy()
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        detections = self.detect_drones(frame_rgb)

        # show text status
        if not detections:
            frame_bgr = self.ui_manager.draw_no_detection_message(frame_bgr)

        # Vision status logic
        if not detections:
            vision_status = "Standby"
        else:
            if self.selected_target_id is not None and any(d['id'] == self.selected_target_id for d in detections):
                vision_status = "Tracking"
            else:
                vision_status = "Detecting"

        # Update vision status to NavBar
        self.nav_bar_widget.setVisionStatus(vision_status)

        # Update status labels ผ่าน UI manager
        motion_mode = "Autonomous" if detections else "Standby"
        self.ui_manager.update_motion_fps_labels(motion_mode, self.current_fps)

        # Center object in the frame
        target = next((d for d in detections if d['id'] == self.selected_target_id), None)
        offset_x = 0
        offset_y = 0
        if target:
            x, y, w_box, h_box = target['bbox']

            # Calculate zoom level from object size
            box_area = w_box * h_box
            max_area = 80000
            zoom = min(1.0, max(0.0, box_area / max_area))
            self.zoom_level = zoom
            self.hud_overlay.set_zoom_level(self.zoom_level)

            # Adjust the zoom and autofocus values from the bounding box.
            self.hud_overlay.auto_adjust_zoom_focus_from_bbox(
                w_box, h_box,
                frame_bgr.shape[1],
                frame_bgr.shape[0]
            )

            # Calculate pitch and update
            obj_cx = x + w_box / 2
            obj_cy = y + h_box / 2
            pitch = 90 - (obj_cy / frame_bgr.shape[0]) * 180
            self.hud_overlay.set_pitch(pitch)

            # Calculate compass and update
            self.compass_bearing = int((obj_cx / frame_bgr.shape[1]) * 360) % 360
            self.hud_overlay.set_heading(self.compass_bearing)

            # Calculate offset and shift image
            screen_cx = frame_bgr.shape[1] // 2
            screen_cy = frame_bgr.shape[0] // 2
            offset_x = int(screen_cx - obj_cx)
            offset_y = int(screen_cy - obj_cy)
            M = np.float32([[1, 0, offset_x], [0, 1, offset_y]])
            frame_bgr = cv2.warpAffine(frame_bgr, M, (frame_bgr.shape[1], frame_bgr.shape[0]))

        # Draw bounding boxes 
        if not hasattr(self, 'detection_labels'):
            self.detection_labels = {}

        for drone in detections:
            x, y, w_box, h_box = drone['bbox']
            x_new = int(x + offset_x)
            y_new = int(y + offset_y)
            
            if 0 <= x_new < frame_bgr.shape[1] and 0 <= y_new < frame_bgr.shape[0]:
                color = (0, 255, 0)
                if self.selected_target_id == drone['id']:
                    color = (0, 0, 255)
                
                # draw bounding box
                cv2.rectangle(frame_bgr, (x_new, y_new), (x_new + w_box, y_new + h_box), color, 1)
                
                # === calculate font size based on bounding box width ===
                zoom_width = w_box
                font_size = max(10, zoom_width // 30) 
                
                # create QLabel if not exists
                if drone['id'] not in self.detection_labels:
                    label = QLabel(self.video_label)
                    label.setAttribute(Qt.WA_TransparentForMouseEvents)
                    self.detection_labels[drone['id']] = label
                label = self.detection_labels[drone['id']]
                
                # update text and style 
                text = f"ID: {drone['id']} {drone['type']} {drone['confidence']:.1f}%"
                label.setText(text)
                label.setStyleSheet(f"""
                    background-color: rgb(60, 60, 60);
                    color: white;
                    border: 0px;
                    border-radius: 0px;
                    padding: 0px;
                    margin: 0px;
                    font-size: {font_size}px;
                    font-family: sans-serif;
                """)
                
                frame_h, frame_w = frame_bgr.shape[:2]
                video_label_w = self.video_label.width()
                video_label_h = self.video_label.height()
                scale_x = video_label_w / frame_w
                scale_y = video_label_h / frame_h
                
                
                font = label.font()
                font.setPixelSize(font_size)
                label.setFont(font)
                
                fm = QFontMetrics(font)
                text_width = fm.horizontalAdvance(text)
                text_height = fm.height()
                
                label.setFixedSize(text_width, text_height)
                
                label_x = int(x_new * scale_x)
                label_y = int(y_new * scale_y - text_height)  # วางเหนือ box พอดี
                
                label_x = max(0, min(label_x, video_label_w - text_width))
                label_y = max(0, label_y)
                
                label.move(label_x, label_y)
                label.show()
                
                # === draw zoom box if needed ===
                if self.zoom_visible:
                    cv2.rectangle(frame_for_zoom, (x, y), (x + w_box, y + h_box), color, 1)

        # === hide unused labels ===
        used_ids = set(d['id'] for d in detections)
        for drone_id in list(self.detection_labels.keys()):
            if drone_id not in used_ids:
                self.detection_labels[drone_id].hide()



        # Show main image
        h, w, _ = frame_bgr.shape
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(frame_rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.video_label.width(), self.video_label.height(), Qt.KeepAspectRatio)
        self.video_label.setPixmap(pixmap)

        # Update HUD
        self.hud_overlay.set_heading(self.compass_bearing)
        self.hud_overlay.update()

        # Zoom View
        if self.zoom_visible:
            target = next((d for d in detections if d['id'] == self.selected_target_id), None)
            if not target and detections:
                target = detections[0]

            if target:
                zoom_frame = frame_for_zoom.copy()
                x, y, w_box, h_box = target['bbox']
                cv2.rectangle(zoom_frame, (x, y), (x + w_box, y + h_box), (0, 0, 255), 1)

                pad = 1.5
                cx, cy = x + w_box // 2, y + h_box // 2
                zw, zh = int(w_box * pad), int(h_box * pad)
                x1, y1 = max(cx - zw // 2, 0), max(cy - zh // 2, 0)
                x2, y2 = min(x1 + zw, zoom_frame.shape[1]), min(y1 + zh, zoom_frame.shape[0])

                zoom_crop = zoom_frame[y1:y2, x1:x2]
                if zoom_crop.size > 0:
                    zoom_view = self.ui_manager.get_widget('zoom_view')
                    zoom_width = zoom_view.width()
                    zoom_height = zoom_view.height()

                    zoom_resized = cv2.resize(zoom_crop, (zoom_width, zoom_height))

                    # text QLabel under zoom view
                    label_text = f"ID:{target['id']} {target['type']} {target['confidence']:.1f}%"
                    zoom_label = self.ui_manager.get_widget('zoom_label_text')
                    zoom_label.setText(label_text)
                    zoom_view = self.ui_manager.get_widget('zoom_view')
                    zoom_width = zoom_view.width()

                    font_size = max(6, zoom_width // 25)

                    font = QFont("Sans Serif", font_size)
                    zoom_label.setFont(font)

                    zoom_label.setStyleSheet("""
                        background-color: rgb(60, 60, 60);
                        color: white;
                        border-radius: 0px;
                        padding: 2px 4px;
                    """)

                    zoom_label.show()

                    zoom_rgb = cv2.cvtColor(zoom_resized, cv2.COLOR_BGR2RGB)
                    zoom_qimage = QImage(
                        zoom_rgb.data,
                        zoom_rgb.shape[1],
                        zoom_rgb.shape[0],
                        zoom_rgb.strides[0],
                        QImage.Format_RGB888
                    )
                    self.ui_manager.set_zoom_view_content(QPixmap.fromImage(zoom_qimage))
        else:
            # hidden zoom label 
            zoom_label = self.ui_manager.get_widget('zoom_label_text')
            zoom_label.hide()

        # Save detections
        self.detected_drone = detections

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            click_pos = event.pos()

            label_w = self.video_label.width()
            label_h = self.video_label.height()

            frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            scale_x = frame_w / label_w
            scale_y = frame_h / label_h

            clicked_x = int(click_pos.x() * scale_x)
            clicked_y = int(click_pos.y() * scale_y)

            for drone in getattr(self, 'detected_drone', []):
                x, y, w, h = drone['bbox']
                if x <= clicked_x <= x + w and y <= clicked_y <= y + h:
                    self.selected_target_id = drone['id']
                    print(f"Selected drone ID: {self.selected_target_id}")
                    return

        elif event.button() == Qt.RightButton:
            # Clear focus
            self.selected_target_id = None
            print("Cleared selected target")

    def detect_drones(self, frame):
        # # RGB to BGR
        # img_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # results = self.yolo_model(img_bgr)

        # detections = []
        # labels, cords = results.xyxyn[0][:, -1], results.xyxyn[0][:, :-1]
        # h, w, _ = frame.shape

        # for i, label in enumerate(labels):
        #     conf = cords[i][4].item()
        #     if conf < 0.3:
        #         continue
        #     x1 = int(cords[i][0].item() * w)
        #     y1 = int(cords[i][1].item() * h)
        #     x2 = int(cords[i][2].item() * w)
        #     y2 = int(cords[i][3].item() * h)
        #     bbox = [x1, y1, x2 - x1, y2 - y1]
        #     class_id = int(label.item())
        #     class_name = self.yolo_model.names[class_id] if hasattr(self.yolo_model, 'names') else "object"

        #     # Rename class
        #     if class_name.lower() == "airplane":
        #         class_name = "drone"

        #     detections.append({
        #         "id": i + 1,
        #         "confidence": conf * 100,
        #         "bbox": bbox,
        #         "type": class_name
        #     })
        # return detections

        return []
    
# Open CSI camera with GStreamer
def gstreamer_pipeline(
    sensor_id=0,
    capture_width=1280,
    capture_height=720,
    display_width=1280,
    display_height=720,
    framerate=30,
    flip_method=0
):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width=(int){capture_width}, height=(int){capture_height}, "
        f"format=(string)NV12, framerate=(fraction){framerate}/1 ! "
        f"nvvidconv flip-method={flip_method} ! "
        f"video/x-raw, width=(int){display_width}, height=(int){display_height}, format=(string)BGRx ! "
        f"videoconvert ! video/x-raw, format=(string)BGR ! appsink"
    )



if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TrackingSystem()
    window.show()
    sys.exit(app.exec_())