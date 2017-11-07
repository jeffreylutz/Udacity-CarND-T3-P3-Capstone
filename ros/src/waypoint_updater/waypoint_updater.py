#!/usr/bin/env python

import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, TwistStamped
from styx_msgs.msg import Lane, Waypoint
import tf

import math
import time

'''
This node will publish waypoints from the car's current position to some `x` distance ahead.

As mentioned in the doc, you should ideally first implement a version which does not care
about traffic lights or obstacles.

Once you have created dbw_node, you will update this node to use the status of traffic lights too.

Please note that our simulator also provides the exact location of traffic lights and their
current status in `/vehicle/traffic_lights` message. You can use this message to build this node
as well as to verify your TL classifier.

TODO (for Yousuf and Aaron): Stopline location for each traffic light.
'''

LOOKAHEAD_WPS = 100  # Number of waypoints we will publish. You can change this number
TIMEOUT_VALUE = 0.1
ONE_MPH = 0.44704


class WaypointUpdater(object):
    def __init__(self):
        rospy.loginfo('WaypointUpdater::__init__ - Start')

        rospy.init_node('waypoint_updater')
        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        rospy.Subscriber('/current_velocity', TwistStamped, self.current_velocity_cb)
        rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        # TODO: Add a subscriber for /traffic_waypoint and /obstacle_waypoint below
        # rospy.Subscriber('/traffic_waypoint', Int32, self.traffic_cb)

        # TODO:  Do we need obstacle detection????
        # rospy.Subscriber('/obstacle_waypoint', , self.obstacle_cb)

        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)

        # TODO: Add other member variables you need below
        self.tf_listener = tf.TransformListener()

        # The car's current position
        self.pose = None

        # The maps's complete waypoints
        self.waypoints = None

        # The car's current velocity
        self.velocity = 0.0

        # first waypoint index at the previous iteration
        self.prev_first_wpt_index = 0

        # Set max speed converting MPH to KPH/mps
        self.max_speed = rospy.get_param('~max_speed', 1) * ONE_MPH

        rospy.spin()

    def pose_cb(self, msg):
        self.pose = msg

        first_wpt_index = -1
        min_wpt_distance = float('inf')
        if self.waypoints is None:
            return

        num_waypoints_in_list = len(self.waypoints.waypoints)

        # Generate an empty lane to store the final_waypoints
        lane = Lane()
        lane.header.frame_id = self.waypoints.header.frame_id
        lane.header.stamp = rospy.Time(0)
        lane.waypoints = []

        # Iterate through the complete set of waypoints until we found the closest
        distance_decreased = False
        # rospy.loginfo('Started at waypoint index: %s', self.prev_first_wpt_index)
        # start_time = time.time()
        for index, waypoint in enumerate(
                        self.waypoints.waypoints[self.prev_first_wpt_index:] + self.waypoints.waypoints[
                                                                               :self.prev_first_wpt_index],
                        start=self.prev_first_wpt_index):
            current_wpt_distance = self.distance(self.pose.pose.position, waypoint.pose.pose.position)
            if distance_decreased and current_wpt_distance > min_wpt_distance:
                break
            if current_wpt_distance > 0 and current_wpt_distance < min_wpt_distance:
                min_wpt_distance = current_wpt_distance
                first_wpt_index = index
                distance_decreased = True
        first_wpt_index %= num_waypoints_in_list

        transformed_light_point = None

        if first_wpt_index == -1:
            rospy.logwarn(
                'WaypointUpdater::waypoints_cb - No waypoints ahead of ego were found... seems that the car went off course')
        else:
            # transform fast avoiding wait cycles
            # Transform first waypoint to car coordinates
            self.waypoints.waypoints[first_wpt_index].pose.header.frame_id = self.waypoints.header.frame_id
            try:
                self.tf_listener.waitForTransform("base_link", "world", rospy.Time(0), rospy.Duration(0.02))
                transformed_waypoint = self.tf_listener.transformPose("base_link",
                                                                      self.waypoints.waypoints[first_wpt_index].pose)
            except (tf.Exception, tf.LookupException, tf.ConnectivityException):
                try:
                    self.tf_listener.waitForTransform("base_link", "world", rospy.Time(0),
                                                      rospy.Duration(TIMEOUT_VALUE))
                    transformed_waypoint = self.tf_listener.transformPose("base_link", self.waypoints.waypoints[
                        first_wpt_index].pose)
                except (tf.Exception, tf.LookupException, tf.ConnectivityException):
                    rospy.logwarn("Failed to find camera to map transform")
                return

            # All waypoints in front of the car should have positive X coordinate in car coordinate frame
            # If the closest waypoint is behind the car, skip this waypoint
            if transformed_waypoint.pose.position.x <= 0.0:
                first_wpt_index += 1
            self.prev_first_wpt_index = first_wpt_index % num_waypoints_in_list

            # Prepare for calculating speed:
            slow_down = False
            reached_zero_velocity = False
            car_distance_to_stop_line = -1.
            planned_velocity = self.max_speed

            # Fill the lane with the final waypoints
            for num_wp in range(LOOKAHEAD_WPS):
                wp = Waypoint()
                wp.pose = self.waypoints.waypoints[(first_wpt_index + num_wp) % num_waypoints_in_list].pose
                wp.twist = self.waypoints.waypoints[(first_wpt_index + num_wp) % num_waypoints_in_list].twist

                wp.twist.twist.linear.x = planned_velocity
                wp.twist.twist.linear.y = 0.0
                wp.twist.twist.linear.z = 0.0

                wp.twist.twist.angular.x = 0.0
                wp.twist.twist.angular.y = 0.0
                wp.twist.twist.angular.z = 0.0
                lane.waypoints.append(wp)

        # finally, publish waypoints as modified on /final_waypoints topic
        self.final_waypoints_pub.publish(lane)

    def current_velocity_cb(self, msg):
        self.velocity = msg.twist.linear.x

    def waypoints_cb(self, waypoints):
        self.waypoints = waypoints

    def traffic_cb(self, msg):
        # TODO: Callback for /traffic_waypoint message. Implement
        pass

    def obstacle_cb(self, msg):
        # TODO: Callback for /obstacle_waypoint message. We will implement it later
        pass

    def get_waypoint_velocity(self, waypoint):
        return waypoint.twist.twist.linear.x

    def set_waypoint_velocity2(self, waypoint, velocity):
        waypoint.twist.twist.linear.x = velocity
        # rospy.logwarn('Waypoint velocity set to: %f', velocity)

    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
        waypoints[waypoint].twist.twist.linear.x = velocity

    def distance(self, waypoints, wp1, wp2):
        dist = 0
        dl = lambda a, b: math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)
        for i in range(wp1, wp2 + 1):
            dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
            wp1 = i
        return dist

    def distance(self, pose1, pose2):
        return math.sqrt((pose1.x - pose2.x) ** 2 + (pose1.y - pose2.y) ** 2 + (pose1.z - pose2.z) ** 2)


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
