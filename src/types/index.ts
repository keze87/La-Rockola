export interface Track {
	artist?: string;
	count?: number;
	display_artist: string;
	display_title: string;
	duration_str?: string;
	duration?: number;
	mood_score?: number;
	path: string;
	title?: string;
}

export interface PlayerState {
	current_track?: string;
	dj_carpincho_enabled?: boolean;
	dj_next_track?: Track | null;
	dj_safe_mode?: boolean;
	duration?: number;
	favorites?: string[];
	history?: string[];
	is_scanning?: boolean;
	library?: Track[];
	mpv_visible?: boolean;
	pause_after_path?: string | null;
	paused?: boolean;
	queue?: string[];
	server_muted?: boolean;
	time_pos?: number;
	top_played?: Track[];
	url_metadata?: Record<string, Track>;
	volume?: number;
}

export interface ApiResponse<T = unknown> {
	status: string;
	data?: T;
	[key: string]: unknown; // Allows flexibility for arbitrary server flags if needed
}

export interface CommandPayloads {
	play: { path: string };
	pause: undefined;
	stop: undefined;
	skip: undefined;
	prev: undefined;
	toggle_queue: { path: string };
	clear_queue: undefined;
	seek: { amount: number };
	seek_absolute: { amount: number };
	set_volume: { vollevel: number };
	set_mute: { state: boolean };
	toggle_favorite: { path: string };
	add_url: { path: string };
	jump: { type: 'queue' | 'history'; index: number };
	remove_queue_item: { index: number };
	move_queue_item: { index: number; new_index: number };
	remove_history_item: { index: number };
	toggle_dj_carpincho: { state: boolean };
	toggle_dj_safe_mode: { state: boolean };
	fullscreen: undefined;
	pause_after: { path: string };
}

export type CommandName = keyof CommandPayloads;
