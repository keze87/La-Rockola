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
