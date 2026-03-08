using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;

public sealed class DotNetTestType
{
    public int Health = 123;
    public float Speed = 1.5f;
    public long Coins = 42;
}

internal static class ObjectAddress
{
    public static unsafe ulong GetAddress(object value)
    {
        TypedReference reference = __makeref(value);
        return (ulong)**(nint**)(&reference);
    }
}

internal static class Program
{
    private static DotNetTestType? keepAlive;
    private static GCHandle keepAliveHandle;

    public static async Task<int> Main()
    {
        try
        {
            GC.TryStartNoGCRegion(1024 * 1024);
        }
        catch (Exception)
        {
        }

        keepAlive = new DotNetTestType();
        keepAliveHandle = GCHandle.Alloc(keepAlive, GCHandleType.Pinned);
        var address = ObjectAddress.GetAddress(keepAlive);
        ulong healthAddress;
        ulong speedAddress;
        ulong coinsAddress;
        unsafe
        {
            fixed (int* healthPointer = &keepAlive.Health)
            fixed (float* speedPointer = &keepAlive.Speed)
            fixed (long* coinsPointer = &keepAlive.Coins)
            {
                healthAddress = (ulong)healthPointer;
                speedAddress = (ulong)speedPointer;
                coinsAddress = (ulong)coinsPointer;
            }
        }
        var payload = new
        {
            pid = Environment.ProcessId,
            process_name = Process.GetCurrentProcess().MainModule?.ModuleName ?? "DotNetTarget.exe",
            address,
            health_address = healthAddress,
            speed_address = speedAddress,
            coins_address = coinsAddress,
        };

        Console.WriteLine(JsonSerializer.Serialize(payload));
        Console.Out.Flush();

        while (true)
        {
            keepAlive.Health += 1;
            keepAlive.Coins += 2;
            await Task.Delay(10);
            GC.KeepAlive(keepAlive);
            GC.KeepAlive(keepAliveHandle);
        }
    }
}
