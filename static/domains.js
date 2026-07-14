// Shared domain configuration — single source of truth for guest + admin UIs.
// To add a new HA entity domain, edit only this file.
const DOMAIN_ORDER = ['light','switch','input_boolean','climate','lock','alarm_control_panel','media_player','cover','fan','button','time','datetime','sensor','binary_sensor'];
const DOMAIN_LABELS = {
  light: 'Lights', switch: 'Switches', input_boolean: 'Switches', climate: 'Climate',
  lock: 'Locks', alarm_control_panel: 'Alarm', media_player: 'Media', cover: 'Covers', fan: 'Fans',
  button: 'Buttons', time: 'Time', datetime: 'Date & Time',
  sensor: 'Sensors', binary_sensor: 'Binary Sensors',
};
const DOMAIN_ICONS = {
  light: 'lightbulb', switch: 'toggle_on', input_boolean: 'toggle_on', climate: 'thermostat',
  lock: 'lock', alarm_control_panel: 'security', media_player: 'speaker', cover: 'blinds', fan: 'mode_fan',
  button: 'radio_button_checked', time: 'schedule', datetime: 'event',
  sensor: 'sensors', binary_sensor: 'motion_sensor_active',
};
const DOMAIN_COLORS = {
  light: { bg: 'bg-amber-500/10', text: 'text-amber-500', icon: 'bg-amber-500' },
  switch: { bg: 'bg-teal-600/10', text: 'text-teal-600', icon: 'bg-teal-600' },
  input_boolean: { bg: 'bg-teal-600/10', text: 'text-teal-600', icon: 'bg-teal-600' },
  climate: { bg: 'bg-blue-500/10', text: 'text-blue-500', icon: 'bg-blue-500' },
  lock: { bg: 'bg-red-500/10', text: 'text-red-500', icon: 'bg-red-500' },
  alarm_control_panel: { bg: 'bg-rose-600/10', text: 'text-rose-600', icon: 'bg-rose-600' },
  media_player: { bg: 'bg-purple-500/10', text: 'text-purple-500', icon: 'bg-purple-500' },
  cover: { bg: 'bg-sky-500/10', text: 'text-sky-500', icon: 'bg-sky-500' },
  fan: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', icon: 'bg-emerald-500' },
  button: { bg: 'bg-orange-500/10', text: 'text-orange-500', icon: 'bg-orange-500' },
  time: { bg: 'bg-indigo-500/10', text: 'text-indigo-500', icon: 'bg-indigo-500' },
  datetime: { bg: 'bg-indigo-500/10', text: 'text-indigo-500', icon: 'bg-indigo-500' },
  sensor: { bg: 'bg-cyan-500/10', text: 'text-cyan-600', icon: 'bg-cyan-600' },
  binary_sensor: { bg: 'bg-lime-500/10', text: 'text-lime-600', icon: 'bg-lime-600' },
};
