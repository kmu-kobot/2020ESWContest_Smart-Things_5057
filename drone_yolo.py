import numpy as np
import time
import cv2
import imutils
from imutils.video import FPS
from imutils.video import VideoStream
from DRONE_Client import *
from MakeMap import *



class Detect_Obj_yolo:
	def __init__(self):
		LABELS_FILE = './yolo/obj.names'
		CONFIG_FILE = './yolo/yolov4-tiny-custom.cfg'
		WEIGHTS_FILE = './yolo/yolo_drone.weights'
		self.CONFIDENCE_THRESHOLD = 0.5
		self.LABELS = open(LABELS_FILE).read().strip().split("\n")
		np.random.seed(4)
		self.COLORS = np.random.randint(0, 255, size=(len(self.LABELS), 3),dtype="uint8")
		self.net = cv2.dnn.readNetFromDarknet(CONFIG_FILE, WEIGHTS_FILE)

		# determine only the *output* layer names that we need from YOLO
		self.ln = self.net.getLayerNames()
		self.ln = [self.ln[i[0] - 1] for i in self.net.getUnconnectedOutLayers()]


	# ....... 0st : 드론 이미지에서 맵만 크롭
	def imgProcessing(self, img):
		make_map = Realize(img)
		make_map.contour()
		make_map.delete_destroy()
		return make_map.img_result

	# ....... 0st : yolo로 객체 확인
	def check_obj_yolo(self, image):
		# 이미지 사이즈 읽어들이기
		blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (416, 416), swapRB=True, crop=False)
		self.net.setInput(blob)
		layerOutputs = self.net.forward(self.ln)

		boxes = []
		confidences = []
		classIDs = []

		# loop over each of the layer outputs
		for output in layerOutputs:
			# loop over each of the detections
			for detection in output:
				# extract the class ID and confidence (i.e., probability) of
				# the current object detection
				scores = detection[5:]
				classID = np.argmax(scores)
				confidence = scores[classID]

				# filter out weak predictions by ensuring the detected
				# probability is greater than the minimum probability
				if confidence > self.CONFIDENCE_THRESHOLD:
					# scale the bounding box coordinates back relative to the
					# size of the image, keeping in mind that YOLO actually
					# returns the center (x, y)-coordinates of the bounding
					# box followed by the boxes' width and height
					box = detection[0:4] * np.array([W, H, W, H])
					(centerX, centerY, width, height) = box.astype("int")

					# use the center (x, y)-coordinates to derive the top and
					# and left corner of the bounding box
					x = int(centerX - (width / 2))
					y = int(centerY - (height / 2))

					# update our list of bounding box coordinates, confidences,
					# and class IDs
					boxes.append([x, y, int(width), int(height)])
					confidences.append(float(confidence))
					classIDs.append(classID)

		# apply non-maxima suppression to suppress weak, overlapping bounding
		# boxes
		idxs = cv2.dnn.NMSBoxes(boxes, confidences, self.CONFIDENCE_THRESHOLD, self.CONFIDENCE_THRESHOLD)
		return boxes, confidences, classIDs, idxs

	# ...... 0-1st : yolo로 파악된 객체의 위치를 라벨링 및 박스 그리기
	def obj_labeling(self, boxes, confidences, classIDs, idxs, image):
		center = []
		for i in idxs.flatten():
			# extract the bounding box coordinates
			(x, y) = (boxes[i][0], boxes[i][1])
			(w, h) = (boxes[i][2], boxes[i][3])
			c_x, c_y = x + w/2, y + h/2
			center.append([c_x, c_y])
			color = [int(c) for c in self.COLORS[classIDs[i]]]

			cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
			text = "{}: {:.4f}".format(self.LABELS[classIDs[i]], confidences[i])
			cv2.putText(image, text, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
		return center[0][0], center[0][1]  # 첫번째로 발견된 객체의 중심점


# .......... yolo 객체 생성
detect_yolo = Detect_Obj_yolo()





H, W = None, None
fps = FPS().start()


# ....... 1st : 서버와 연결 및 필요한 객체들 생성
TCP_IP = 'localhost'
TCP_PORT = 5009
drone_client = DRONE_Client(TCP_IP, TCP_PORT)




# ....... 2nd : 서버에 이미지 전송 시도
successFrame = 0
vs = cv2.VideoCapture("./container/drone1.mp4")
while vs.isOpened:
	_, image = vs.read()
	img_origin = image

	# 이미지 사이즈 읽어들이기
	if W is None or H is None:
		H, W = image.shape[:2]

	# yolo를 이용하여 객체가 있는지 확인 후 있다면 위치를 담는다
	boxes, confidences, classIDs, idxs = detect_yolo.check_obj_yolo(image)
	# ensure at least one detection exists
	if True:# len(idxs) > 0:
					# ....... 3rd : 이미지에 전체 맵이 담았는지 판단 - 이미지 & 객체 위치
					correctMap = drone_client.fullMapChecker(img_origin)
					# ....... 4th : 이미지가 전체 맵을 담았다고 판단되면 서버에 전송
					if correctMap:
							# ...... 4.0 : 왜곡된 사진에서 맵만 추출
							image = detect_yolo.imgProcessing(image)
							# ...... 4.1 : yolo를 이용하여 객체 위치 다시 update
							boxes, confidences, classIDs, idxs = detect_yolo.check_obj_yolo(image)
							if True:#len(idxs) > 0:
									print("좌표상에서 객체의 위치를 구합니다.")
									c_x, c_y = 75, 75
									#c_x, c_y = detect_yolo.obj_labeling(boxes, confidences, classIDs, idxs, image)
									print("sending")
									cv2.imwrite("test.jpg", cv2.resize(image, (800, 600)))
									drone_client.sendToServer(img_origin, (c_x, c_y))
									successFrame += 1


	# ....... 5th : 보낸 이미지가 3장이면 서버로부터 응답 기다리기
	if successFrame == 3:
		print("___________서버로부터 답변을 기다리고 있습니다.___________")
		data = drone_client.sockWaitAnswer()
		print(data)
		if data == 'DRONE_again':
			successFrame = 0
			print("객체를 다시 추적합니다.")
		elif data == 'DRONE_close':
			print("객체 찾기 모드를 종료합니다.")
			drone_client.sockClose()

	fps.update()

	# show the output image
	cv2.imshow("output", cv2.resize(image, (800, 600)))
	if cv2.waitKey(1) & 0xFF == ord("q"):
		break




fps.stop()

print("[INFO] elasped time: {:.2f}".format(fps.elapsed()))
print("[INFO] approx. FPS: {:.2f}".format(fps.fps()))

# do a bit of cleanup
cv2.destroyAllWindows()

# release the file pointers
print("[INFO] cleaning up...")
vs.release()
