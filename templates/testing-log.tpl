% include('templates/header.tpl', title='Series')

<ul class="list-group">
    <li class="list-group-item"><strong>{{series['subject']}}</strong></li>
    %for i in series['patches']:
        %if i['message-id'] != series['message-id']:
            <li class="list-group-item" style="padding-left: 30px">{{i['subject']}}</li>
        %end
    %end
</ul>

<h3>
    %if series.get('merged'):
        <span class="label label-primary">Merged</span>
    %elif series['testing-passed']:
        <span class="label label-success">Passed</span>
    %else:
        <span class="label label-danger">Failed</span>
    %end
</h3>
<br>
<pre>{{log}}</pre>

% include('templates/footer.tpl')
