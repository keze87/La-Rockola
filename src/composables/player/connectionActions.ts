export type ReconnectSocketOptions = { onlyIfActive?: boolean };
export type ReconnectSocketHandler = (opts?: ReconnectSocketOptions) => void;

let reconnectHandler: ReconnectSocketHandler | null = null;

/** Registra el handler de reconexión de WebSocket sin acoplar useAndroidHost a useSocket. */
export function registerSocketReconnectHandler(handler: ReconnectSocketHandler): void {
	reconnectHandler = handler;
}

/** Solicita reconectar el WebSocket activo al origen actual si ya fue inicializado. */
export function requestSocketReconnect(opts?: ReconnectSocketOptions): void {
	reconnectHandler?.(opts);
}
