"""
getTarget.py

This file should contain most of the math-heavy functions
    for use in an eventual prototype

By far the most dificult part of this project so far has been
    interfacing with the gdal library for GEOINT data

This file will focus instead on the core math of resolving the location
    of a target in the UAS camera's direct center line-of-sight
    ...while under the assumption that getAltFromLatLong() abstracts
       away the GEOINT data implementation

See ../fn_diagram.jpg

"""

import time
import matplotlib.pyplot as plt
from osgeo import gdal
import math
from math import sin, asin, cos, atan2, sqrt
from geotiff_play import *
import sys

"""get the pos of current subject of UAS camera
       implementation can be changed later
"""
def getTarget():
    print("Hello World!")
    print("I'm getTarget.py")
    print("Which GeoTiff file would you like to read?")
    geoFile = None
    while geoFile is None:
        geofilename = str(input("Enter the GeoTIFF filename: "))
        geofilename.strip()
        if geofilename.isdecimal() or geofilename.isnumeric():
            print(f'ERROR: filename {geofilename} does not contain at least 1 non-digit character')
            print('Please try again')
            continue
        else:
            try:
                geoFile = gdal.Open(geofilename)
            except:
                print(f'ERROR: can\'t find file with name \'{geofilename}\'')
                geoFile = None
                print('Please try again')
                continue
    #

    band = geoFile.GetRasterBand(1)
    elevationData = band.ReadAsArray()
    print("The shape of the elevation data is: ", elevationData.shape)
    print("The raw Elevation data is: ")
    print(elevationData)

    nrows, ncols = elevationData.shape

    # I'm making the assumption that the image isn't rotated/skewed/etc.
    # This is not the correct method in general, but let's ignore that for now
    # If dxdy or dydx aren't 0, then this will be incorrect
    x0, dx, dxdy, y0, dydx, dy = geoFile.GetGeoTransform()

    # we cannot deal with rotated or skewed images in current version
    if dxdy != 0 or dydx != 0:
        outstr = "FATAL ERROR: geoTIFF is rotated or skewed!"
        outstr += "\ncannot proceed with file: "
        outstr += geofilename
        print(outstr, file=sys.stderr)
        sys.exit(outstr)

    x1 = x0 + dx * ncols
    y1 = y0 + dy * nrows

    print(f'x0: {round(x0,4)} dx: {round(dx,9)} ncols: {round(ncols,4)} x1: {round(x1,4)}')
    print(f'y0: {round(y0,4)} dy: {round(dy,9)} nrows: {round(nrows,4)} y1: {round(y1,4)}')

    xParams = (x0, x1, dx, ncols)
    yParams = (y0, y1, dy, nrows)

    # note that by convention, coord pairs are usually (lat,long)
    #     i.e. (y,x)
    y = inputNumber("Please enter aircraft latitude in (+/-) decimal form: ", y1, y0)
    x = inputNumber("Please enter aircraft longitude in (+/-) decimal form: ", x0, x1)
    z = inputNumber("Please enter altitude (meters from sea-level) in decimal form: ", -423, 8848)
    azimuth = inputNumber("Please enter camera azimuth (0 is north) in decimal form (degrees): ", 0, 360)
    theta = inputNumber("Please enter angle of declanation (degrees down from forward) in decimal form: ", 0, 90)

    # most of the complex logic is done here
    target = resolveTarget(y, x, z, azimuth, theta, elevationData, xParams, yParams)

    finalDist, tarY, tarX, tarZ, terrainAlt = target
    print(f'Approximate range to target: {finalDist}')
    print(f'Target lat: {tarY}')
    print(f'Target lon: {tarX}')
    print(f'Approximate alt (constructed): {tarZ}')
    print(f'Approximate alt (terrain): {terrainAlt}')


# handle user input of data, using message for prompt
#   guaranteed to return a float
def inputNumber(message, lowerBound, upperBound):
    while True:
        try:
            userInput = float(input(message))
            if userInput < lowerBound or upperBound < userInput:
                print(f'ERROR: input out of bounds. Lower bound is {lowerBound}, Upper bound is {upperBound}')
                print("Please Try Again")
                continue
        except ValueError:
            print("ERROR: Not an decimal number! Try again.")
            continue
        else:
            return userInput
            break

"""given sensor data, returns a tuple (y, x, z) location of target

Parameters
----------
y : float
    latitude of aircraft
x : float
    longitude of aircraft
z : float
    altitude of aircraft, meters from sea level
    accuracy is greatly improved on most aircraft with
    barometric sensor, sometimes ultrasonic sensors too
azimuth : float
    azimuth represents the direction of the aircraft's camera
    measured in degrees
    starting from North @ 0°, increasing clockwise (e.g. 90° is East)
    usually an integer value, but must be between 0.0 and 360.0
theta : float
    theta represents the angle of declanation of the aircraft's camera
    measured in degrees
    starting at 0° as ideal level with the horizon, increasing as it aims downward
    must be between 0.0 (straight forward) and 90.0 (straight downward)
elevationData : 2D array
    elevationData
xParams: tuple
     tuple of 4 elements (x0, x1, dx, ncols)
     x0 is minimum lon. of dataset
     x1 is maximum lon. of dataset
     dx is the lon. change per datapoint increment +x
     ncols is the number of datapoints per row of the dataset
yParams: tuple
     tuple of 4 elements (y0, y1, dy, nrows)
     y0 is maximum lat. of dataset
     y1 is minimum lat. of dataset
     dy is the lat. change per datapoint increment +y
     nrows is the number of datapoints per column of the dataset

"""
def resolveTarget(y, x, z, azimuth, theta, elevationData, xParams, yParams):

    # convert azimuth and theta from degrees to radians
    azimuth, theta = math.radians(azimuth), math.radians(theta)

    # direction, convert to unit circle (just like math class)
    direction = azimuthToUnitCircleRad(azimuth)

    # from Azimuth, determine rate of x and y change
    #     per unit travel (level with horizon for now)
    deltax, deltay = math.cos(direction), math.sin(direction)

    deltaz = -1 * math.sin(theta) #neg because direction is downward


    # determines by how much of travel per unit is actually horiz
    # pythagoran theorem, deltaz^2 + deltax^2 + deltay^2 = 1
    horizScalar = math.cos(theta)
    deltax, deltay = horizScalar * deltax, horizScalar * deltay

    # at this point, deltax^2 + deltay^2 + deltaz^2 = 1
    #     if not, something is wrong
    sumOfSquares = deltax*deltax + deltay*deltay + deltaz*deltaz
    print(f'sum of squares is 1.0 : {sumOfSquares == 1.0}')
    print(f'deltax is {round(deltax, 4)}')
    print(f'deltay is {round(deltay, 4)}')
    print(f'deltaz is {round(deltaz, 4)}')

    x0 = xParams[0]
    x1 = xParams[1]

    y0 = yParams[0]
    y1 = yParams[1]

    dx = xParams[2]
    #meters of acceptable distance between constructed line and datapoint
    threshold = abs(dx) / 4

    #meters of increment for each stepwise check (along constructed line)
    increment = 1

    # start at the aircraft's position
    curY = y
    curX = x
    curZ = z
    altDiff = curZ - getAltFromLatLon(curY, curX, xParams, yParams, elevationData)
    while altDiff > threshold:
        groundAlt = getAltFromLatLon(curY, curX, xParams, yParams, elevationData)
        altDiff = curZ - groundAlt

        avgAlt = curZ
        # deltaz should always be negative
        curZ += deltaz
        avgAlt = (avgAlt + curZ) / 2
        curY, curX = inverse_haversine((curY,curX), math.cos(theta)*increment, azimuth, avgAlt)
        #check for Out Of Bounds after each iteration
        if curY > y0 or curY < y1 or curX < x0 or curX > x1:
            print(f'FATAL ERROR: resolveTarget ran out of bounds at {curY}, {curX}, {curZ}m')
            errOut = "FATAL ERROR: Please ensure target location is within geoTIFF dataset bounds"
            print(errOut, file=sys.stderr)
            sys.exit(errOut)
        #
        #end iteration
    #end loop
    #
    #When the loop ends, curY, curX, and curZ are closeish to the target
    #may be a bit biased to slightly long (beyond the target)
    #this algorithm is extremely crude, NOT ACCURATE!
    #    could use refinement

    # print(f'Final stepwise Alt dist: {altDiff}')
    finalHorizDist = abs(haversine(x, y, curX, curY, z))
    finalVertDist = abs(z - curZ)
    # simple pythagorean theorem
    finalDist = sqrt(finalHorizDist ** 2 + finalVertDist ** 2)
    terrainAlt = getAltFromLatLon(curY, curX, xParams, yParams, elevationData)

    # print(f'Approximate range to target: {finalDist}')
    # print(f'Target lat: {curY}')
    # print(f'Target lon: {curX}')
    # print(f'Approximate alt (constructed): {curZ}')

    # print(f'Approximate alt (terrain): {terrainAlt}')
    return((finalDist, curY, curX, curZ, terrainAlt))

# convert from azimuth notation (0 is up [+y], inc. clockwise) to
#     math notation(0 is right [+x], inc. counter-clockwise)
#
#     all units in Radians
def azimuthToUnitCircleRad(azimuth):
    # reverse direction of increment
    direction = (-1 * azimuth)
    # rotate 90deg, move origin from +y to +x
    direction += (0.5 * math.pi)
    direction = normalize(direction)
    print(f'direction is: {math.degrees(direction)}')
    return direction

# if a given angle is not between 0 and 2pi,
#     return the same angle in a number that is between 0 and 2pi (rad)
def normalize(direction):
    # the following two routines are mutually-exclusive
    while (direction < 0):
        direction += 2 * math.pi
    while (direction > (2 * math.pi)):
        direction -= 2 * math.pi

    return direction

# Inverse Haversine formula
# adapted from user github.com/jdeniau
# not verified accurate
# given a point, distance, and direction, return the new point (lat lon)
def inverse_haversine(point, distance, azimuth, alt):
    lat, lon = point
    lat, lon = map(math.radians, (lat, lon))
    d = distance
    r = 6371000 + alt # average radius of earth + altitude
    # Note: here we use azimuth (start @ 0, inc. clockwise),
    #       NOT like unit circle!
    brng = azimuth

    return_lat = asin(sin(lat) * cos(d / r) + cos(lat) * sin(d / r) * cos(brng))
    return_lon = lon + atan2(sin(brng) * sin(d / r) * cos(lat), cos(d / r) - sin(lat) * sin(return_lat))

    return_lat, return_lon = map(math.degrees, (return_lat, return_lon))
    return return_lat, return_lon

# Haversine formula
# i.e. great circle distance (meters) between two lat lon
# via stackoverflow.com/a/4913653
def haversine(lon1, lat1, lon2, lat2, alt):
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    # en.wikipedia.org/wiki/Earth_radius
    r = 6371000 + alt # Radius of earth in meters. Use 3956 for miles. Determines return value units.
    return c * r

if __name__ == "__main__":
    getTarget()
