import threading
import time
import os
import cv2
import numpy as np
import sys, getopt
import caffe
GPU_ID = 0  # Switch between 0 and 1 depending on the GPU you want to use.
# caffe.set_mode_gpu()
# caffe.set_device(GPU_ID)
caffe.set_mode_cpu()


cores_preprocess_max = 8#2
cores_yolo_max = 8#5

cores_preprocess_current = []
cores_yolo_current = []

imageData = []
savedImagesPaths = []
fpses = []

global saveThreadCounter
saveThreadCounter = 0
global imagesProcessed
imagesProcessed = 0
global StartTime
StartTime = 0


def loadImages(inputFile):
  path = "/home/ryan/Documents/Summer_Research/CAM2SmallScale/"
  for line in inputFile:
    wholeName = path + line
    try:
      frame = cv2.imread(wholeName)
      frame = cv2.resize(frame, (448,448))
      imageData.append(frame)
    except:
      print ("Bad Frame")
      pass
  cores_download_current.pop()


def loadAnalysis():
  print ("Loading network")
  model_filename = "prototxt/yolomkl2017.prototxt"
  weight_filename = "yolo_small.caffemodel"

  net = caffe.Net(model_filename, weight_filename, caffe.TEST)

  transformer = caffe.io.Transformer({'data': net.blobs['data'].data.shape})
  transformer.set_transpose('data', (2, 0, 1))

  print ("Starting neural network threads")
  for x in range(cores_yolo_max):
    t = threading.Thread(target=analyze, args=(net, transformer,))
    t.start()

def analyze(net, transformer):
  try:
    while True:
      breaker = False
      # img_filename = savedImagesPaths.pop()
      # img = caffe.io.load_image(img_filename)  # load the image using caffe io
      img = imageData.pop()
      # ti = time.time()
      array = transformer.preprocess('data', img)
      # print ("\t\t\tPreprocess Time" + str(time.time() - ti))

      # ti = time.time()
      out = net.forward_all(data=np.asarray([array]))
      # print ("\t\t\t\t\t\t\t\tForwarding Time: " + str(time.time()-ti))

      global imagesProcessed
      imagesProcessed += 1

      global startTime
      avg_fps = imagesProcessed / (time.time()-startTime)
      print '\nIMG: {0} \tAvg FPS: {1}'.format(str(imagesProcessed), str(avg_fps)[:5])
      results = interpret_output(out['result'][0], img.shape[1], img.shape[0])  # fc27 instead of fc12 for yolo_small
      show_results(results)
      if (len(imageData) <= 0):
        print ("Thread Exiting")
        exit()
  except KeyboardInterrupt:
    print ("Exiting")
    exit()


def interpret_output(output, img_width, img_height):
  classes = ["aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
             "dog", "horse", "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"]
  w_img = img_width
  h_img = img_height
  # print w_img, h_img
  threshold = 0.2
  iou_threshold = 0.5
  num_class = 20
  num_box = 2
  grid_size = 7
  probs = np.zeros((7, 7, 2, 20))
  class_probs = np.reshape(output[0:980], (7, 7, 20))
  #	print class_probs
  scales = np.reshape(output[980:1078], (7, 7, 2))
  #	print scales
  boxes = np.reshape(output[1078:], (7, 7, 2, 4))
  offset = np.transpose(np.reshape(np.array([np.arange(7)] * 14), (2, 7, 7)), (1, 2, 0))

  boxes[:, :, :, 0] += offset
  boxes[:, :, :, 1] += np.transpose(offset, (1, 0, 2))
  boxes[:, :, :, 0:2] = boxes[:, :, :, 0:2] / 7.0
  boxes[:, :, :, 2] = np.multiply(boxes[:, :, :, 2], boxes[:, :, :, 2])
  boxes[:, :, :, 3] = np.multiply(boxes[:, :, :, 3], boxes[:, :, :, 3])

  boxes[:, :, :, 0] *= w_img
  boxes[:, :, :, 1] *= h_img
  boxes[:, :, :, 2] *= w_img
  boxes[:, :, :, 3] *= h_img

  for i in range(2):
    for j in range(20):
      probs[:, :, i, j] = np.multiply(class_probs[:, :, j], scales[:, :, i])
  filter_mat_probs = np.array(probs >= threshold, dtype='bool')
  filter_mat_boxes = np.nonzero(filter_mat_probs)
  boxes_filtered = boxes[filter_mat_boxes[0], filter_mat_boxes[1], filter_mat_boxes[2]]
  probs_filtered = probs[filter_mat_probs]
  classes_num_filtered = np.argmax(probs, axis=3)[filter_mat_boxes[0], filter_mat_boxes[1], filter_mat_boxes[2]]

  argsort = np.array(np.argsort(probs_filtered))[::-1]
  boxes_filtered = boxes_filtered[argsort]
  probs_filtered = probs_filtered[argsort]
  classes_num_filtered = classes_num_filtered[argsort]

  for i in range(len(boxes_filtered)):
    if probs_filtered[i] == 0: continue
    for j in range(i + 1, len(boxes_filtered)):
      if iou(boxes_filtered[i], boxes_filtered[j]) > iou_threshold:
        probs_filtered[j] = 0.0

  filter_iou = np.array(probs_filtered > 0.0, dtype='bool')
  boxes_filtered = boxes_filtered[filter_iou]
  probs_filtered = probs_filtered[filter_iou]
  classes_num_filtered = classes_num_filtered[filter_iou]

  result = []
  for i in range(len(boxes_filtered)):
    result.append(
      [classes[classes_num_filtered[i]], boxes_filtered[i][0], boxes_filtered[i][1], boxes_filtered[i][2],
       boxes_filtered[i][3], probs_filtered[i]])

  return result


def iou(box1, box2):
  tb = min(box1[0] + 0.5 * box1[2], box2[0] + 0.5 * box2[2]) - max(box1[0] - 0.5 * box1[2],
                                                                   box2[0] - 0.5 * box2[2])
  lr = min(box1[1] + 0.5 * box1[3], box2[1] + 0.5 * box2[3]) - max(box1[1] - 0.5 * box1[3],
                                                                   box2[1] - 0.5 * box2[3])
  if tb < 0 or lr < 0:
    intersection = 0
  else:
    intersection = tb * lr
  return intersection / (box1[2] * box1[3] + box2[2] * box2[3] - intersection)


def show_results(results):
  for i in range(len(results)):
    x = int(results[i][1])
    y = int(results[i][2])
    aw = int(results[i][3]) / 2
    ah = int(results[i][4]) / 2
    print '\t\t\t\t\tclass: ' + results[i][0] + ' ' + str(x-aw) + ',' + str(y-ah) + ',' + str(int(results[i][3])) + ',' + str(int(results[i][4])) + '], Conf: ' + (str(results[i][5]))[:6]

if __name__ == '__main__':
  saveThreadCounter = 0
  # Initial loading of threads
  ti = time.time()

  inputFile = open("images.txt", 'r')

  loadImages(inputFile)

  # Load yolo model and start analysis
  loadAnalysis()

